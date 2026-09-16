/******************************************************************************
This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*******************************************************************************/

#ifndef __ASTRA_SIM_NS3_EXPERIMENT_CONFIG_HH__
#define __ASTRA_SIM_NS3_EXPERIMENT_CONFIG_HH__

#include "astra-sim/system/Common.hh"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <initializer_list>
#include <limits>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

#include <json/json.hpp>

namespace AstraSimNs3 {

constexpr uint64_t kDecisionScale = 1000000;
constexpr uint16_t kPriorityGroupCount = 8;

inline uint64_t mix_hash(uint64_t value) {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

inline void hash_combine(uint64_t& hash, uint64_t value) {
    hash = mix_hash(hash ^ mix_hash(value));
}

enum class FlowKind : uint8_t {
    ForegroundPayload = 0,
    ProvenanceControl,
    BackgroundMicroburst,
};

enum class FlowTerminalOutcome : uint8_t {
    Pending = 0,
    Completed,
    Failed,
};

// Where the phase-aware budget is spent. Admission decides before a payload is
// offered and substitutes the whole message. Recovery decides after a switch
// has already trimmed a packet and lets that packet's bytes go, which is the
// only point at which the policy can act during a congestion episode.
// RecoveryExempt forgives the same way and additionally lets an eligible flow
// ignore congestion signals until the receiver refuses to forgive one of its
// trims, so the budget is paid in bounded loss rather than in rate.
enum class SheddingDomain : uint8_t {
    Admission = 0,
    Recovery,
    RecoveryExempt,
};

// Whether a domain decides after the trim. The one eliminator every test of
// "is this a forgiving domain" goes through, exhaustive so that a fourth
// variant fails to compile here rather than falling through to admission.
constexpr bool forgives(SheddingDomain domain) {
    switch (domain) {
        case SheddingDomain::Admission:
            return false;
        case SheddingDomain::Recovery:
            return true;
        case SheddingDomain::RecoveryExempt:
            return true;
    }
    return false;
}

// The semantics string a profile must name for its domain. Exhaustive for the
// same reason: the string is the contract the generator writes and this reads.
constexpr const char* selection_semantics(SheddingDomain domain) {
    switch (domain) {
        case SheddingDomain::Admission:
            return "logical_admission_selection";
        case SheddingDomain::Recovery:
            return "recovery_forgiveness";
        case SheddingDomain::RecoveryExempt:
            return "recovery_forgiveness_cc_exempt";
    }
    return "";
}

// What the transport should do with one trimmed range, and what the receiver
// reports about the budget entry it belongs to. Two bits, because a repair is
// "not forgive" and room is "not spent", and because the charge that empties
// an entry is a forgiveness. The values cross into ns-3 as
// RdmaHw::RecoveryVerdict and must not drift from it.
enum : uint8_t {
    kForgive = 1 << 0,
    kAllowanceSpent = 1 << 1,
};

constexpr bool forgave(uint8_t verdict) {
    return verdict & kForgive;
}

constexpr bool revokes_exemption(uint8_t verdict) {
    return verdict & kAllowanceSpent;
}

// One receiving rank's budget for one training step. Every counter is
// monotone and forgiven + delivered never exceeds eligible.
struct StepLedger {
    uint64_t eligible = 0;
    uint64_t shed = 0;
    uint64_t forgiven = 0;
    // Bytes of completed messages, less the bytes those messages were
    // forgiven. Vesting measures the budget against this rather than against
    // what was merely launched.
    uint64_t delivered = 0;
    // Set when the rank has written its DP All-Reduce row for the step. After
    // that the step's bytes are accounted for and nothing more may be
    // forgiven against them.
    bool closed = false;
};

// The pacing rule, as a closed sum. Pacing lets the receiver decline a
// forgivable trim so that allowance remains for later in the step, because
// the cap binds at the headline budget and first come first served spends it
// on the first burst. A Bernoulli probability is meaningful only under
// Bernoulli, so it lives inside that alternative and nowhere else.
struct NoPacing {};
struct Bernoulli {
    uint64_t threshold = 0;  // p * kDecisionScale
};
struct Vesting {};
using Pacing = std::variant<NoPacing, Bernoulli, Vesting>;

// std::visit over a lambda set. Every visit below lists all three
// alternatives, so a fourth one fails to compile rather than defaulting.
template <class... Cases>
struct overloaded : Cases... {
    using Cases::operator()...;
};
template <class... Cases>
overloaded(Cases...) -> overloaded<Cases...>;

// The bytes the rule measures its budget against. Vesting is strictly tighter
// than the other two because delivered never exceeds eligible, so the ceiling
// is unchanged and only its availability moves.
inline uint64_t pacing_base(const StepLedger& cell, const Pacing& pacing) {
    return std::visit(
        overloaded{
            [&](const NoPacing&) { return cell.eligible; },
            [&](const Bernoulli&) { return cell.eligible; },
            [&](const Vesting&) { return cell.delivered; },
        },
        pacing);
}

// Whether the rule declines a range the cap could still afford. The coin
// reserves allowance for the end of the step; the other two rules reserve
// nothing and never decline.
inline bool paces_out(const Pacing& pacing, uint64_t coin) {
    return std::visit(
        overloaded{
            [](const NoPacing&) { return false; },
            [&](const Bernoulli& rule) { return coin >= rule.threshold; },
            [](const Vesting&) { return false; },
        },
        pacing);
}

// The safety law, in one place: shed and forgiven bytes share one budget, and
// the budget is the step's threshold times the rule's own denominator.
// Absorbing: neither term ever decreases, so a range charged once is never
// refunded.
inline bool affords(const StepLedger& cell,
                    uint64_t threshold,
                    const Pacing& pacing,
                    uint64_t bytes) {
    const uint64_t spent = cell.shed + cell.forgiven + bytes;
    return spent * kDecisionScale <= pacing_base(cell, pacing) * threshold;
}

// The coin one trimmed range draws. Deterministic per range, so a range the
// coin refuses stays refused on re-trim and "forgive a fraction p of trimmed
// ranges" is exact rather than geometric. No ns-3 random stream is consumed,
// so paired arms stay paired.
inline uint64_t range_coin(uint64_t decision_hash, uint64_t start) {
    uint64_t coin = decision_hash;
    hash_combine(coin, start);
    return coin % kDecisionScale;
}

// Trim verdict. Pure and total: the cell, the rule and this range's coin in,
// the two verdict bits and the cell to store out. The caller has already
// eliminated a missing or closed cell and an ineligible flow.
//
// The allowance report says the cell cannot take the range in front of it.
// After a charge the smallest further range is one byte, so that is what the
// cell is asked about; after a refusal the refused range is its own evidence.
inline std::pair<uint8_t, StepLedger> trim_verdict(StepLedger cell,
                                                   uint64_t threshold,
                                                   const Pacing& pacing,
                                                   uint64_t coin,
                                                   uint64_t bytes) {
    const bool forgive =
        affords(cell, threshold, pacing, bytes) && !paces_out(pacing, coin);
    if (forgive) {
        cell.forgiven += bytes;
    }
    const bool room = affords(cell, threshold, pacing, forgive ? 1 : bytes);
    const uint8_t verdict = static_cast<uint8_t>((forgive ? kForgive : 0) |
                                                 (room ? 0 : kAllowanceSpent));
    return {verdict, cell};
}

// Remainder verdict. Pure and total: the bytes to forgive, zero to refuse.
// Whole remainder or nothing, because the receiver knows the byte count and
// not which gradient elements matter, so it does not choose among them. The
// coin never applies here: pacing exists to keep allowance for the end of the
// step, and applying it at the end of the step would defeat its own purpose.
inline std::pair<uint64_t, StepLedger> remainder_verdict(StepLedger cell,
                                                         uint64_t threshold,
                                                         const Pacing& pacing,
                                                         uint64_t remainder) {
    if (remainder == 0 || !affords(cell, threshold, pacing, remainder)) {
        return {uint64_t{0}, cell};
    }
    cell.forgiven += remainder;
    return {remainder, cell};
}

// Dense (receiving rank, step) budget table. Ranks stay under a few hundred
// and steps under a few hundred, so the whole table is well under a megabyte
// and every access is one multiply-add. A default-constructed ledger is empty
// and total: every query answers "do not forgive" and every update is a
// no-op, which is exactly the admission domain's behaviour.
class ForgivenessLedger {
  public:
    ForgivenessLedger() = default;

    static ForgivenessLedger make(uint32_t ranks, uint32_t steps) {
        ForgivenessLedger ledger;
        if (ranks == 0 || steps == 0) {
            return ledger;
        }
        ledger.ranks_ = ranks;
        ledger.steps_ = steps;
        ledger.cells_.assign(static_cast<size_t>(ranks) * steps, StepLedger{});
        return ledger;
    }

    bool empty() const {
        return cells_.empty();
    }

    void register_eligible(uint32_t dst, uint32_t step, uint64_t bytes) {
        if (StepLedger* cell = find(dst, step)) {
            cell->eligible += bytes;
        }
    }

    void register_shed(uint32_t dst, uint32_t step, uint64_t bytes) {
        if (StepLedger* cell = find(dst, step)) {
            cell->shed += bytes;
        }
    }

    // What a completed message left behind, which is what vesting spends.
    void register_delivered(uint32_t dst, uint32_t step, uint64_t bytes) {
        if (StepLedger* cell = find(dst, step)) {
            cell->delivered += bytes;
        }
    }

    // Closing a cell also asserts the contract on it; the definition sits
    // beside the verdicts, below, because the threshold it holds the cell to
    // comes from the same mask they charged it against.
    void close(uint32_t dst, uint32_t step);

    // The one eliminator for a cell a verdict may be computed on, and the
    // only reader of `closed`. Null means the rank or step is outside the
    // table, or the rank has already written its row for the step, and both
    // answer "repair, with nothing to report about the allowance".
    StepLedger* open_cell(uint32_t dst, uint32_t step) {
        StepLedger* cell = find(dst, step);
        return (cell != nullptr && !cell->closed) ? cell : nullptr;
    }

    const StepLedger* cell(uint32_t dst, uint32_t step) const {
        return find(dst, step);
    }

  private:
    // Steps are one-based in every profile, mask, and telemetry row.
    StepLedger* find(uint32_t dst, uint32_t step) {
        return const_cast<StepLedger*>(
            const_cast<const ForgivenessLedger*>(this)->find(dst, step));
    }

    const StepLedger* find(uint32_t dst, uint32_t step) const {
        if (dst >= ranks_ || step == 0 || step > steps_) {
            return nullptr;
        }
        return &cells_[static_cast<size_t>(dst) * steps_ + (step - 1)];
    }

    uint32_t ranks_ = 0;
    uint32_t steps_ = 0;
    std::vector<StepLedger> cells_;
};

struct MicroburstFlow {
    uint32_t src = 0;
    uint32_t dst = 0;
    uint64_t size_bytes = 0;
    uint64_t offset_ns = 0;
    uint16_t priority_group = 3;
};

struct ExperimentConfig {
    bool enabled = false;
    uint64_t seed = 0;
    // Provenance only. The selection hash excludes it so two profiles that
    // differ only by name draw the same selection stream and stay matched.
    std::string run_id = "default";
    uint16_t default_priority_group = 3;
    uint16_t provenance_priority_group = 1;
    uint64_t provenance_control_bytes = 64;
    std::map<uint32_t, uint16_t> vnet_to_priority_group;
    std::map<uint32_t, uint64_t> shedding_threshold_by_step;
    bool selection_policy_configured = false;
    SheddingDomain domain = SheddingDomain::Admission;
    uint64_t p_low_threshold = 0;
    uint64_t p_high_threshold = 0;
    // The receiver's two v2 policies. Pacing reserves allowance for later in
    // the step; the straggler idle is how long a receive queue pair must go
    // quiet before the receiver offers to forgive the unsent remainder, with
    // zero meaning "ask at every arrival" and no value meaning disabled.
    Pacing pacing = NoPacing{};
    std::optional<uint64_t> straggler_idle_ns;
    uint32_t rank_count = 0;
    uint32_t step_count = 0;
    bool clr_mask_configured = false;
    std::map<uint32_t, bool> clr_mask_by_step;
    bool microburst_enabled = false;
    uint32_t microburst_trigger_step = 2;
    std::vector<MicroburstFlow> microburst_flows;
    bool microburst_triggered = false;
    // Where the telemetry will be written. Empty when no experiment is
    // configured. The files are not opened here: see open_experiment_telemetry.
    std::string telemetry_output_dir;
};

struct SheddingDecision {
    bool eligible = false;
    bool shed = false;
    bool is_clr = false;
    uint64_t decision_hash = 0;
};

struct FlowRecord {
    FlowKind kind = FlowKind::ForegroundPayload;
    bool shed = false;
    bool admission_eligible = false;
    AstraSim::TransportRole origin_transport_role =
        AstraSim::TransportRole::Unknown;
    AstraSim::OperationContext operation;
    uint64_t decision_hash = 0;
    int src = 0;
    int dst = 0;
    int tag = 0;
    uint16_t source_port = 0;
    uint16_t priority_group = 0;
    uint64_t logical_bytes = 0;
    uint64_t physical_bytes = 0;
    uint64_t data_attempted_bytes = 0;
    uint64_t retransmitted_bytes = 0;
    uint64_t trimmed_payload_bytes = 0;
    uint32_t recovery_events = 0;
    uint32_t trim_notifications = 0;
    uint32_t trim_lasthop_notifications = 0;
    uint32_t trim_recovery_events = 0;
    uint32_t stale_trim_notifications = 0;
    uint32_t timeouts = 0;
    uint32_t cnp_received = 0;
    // Bytes the receiver accepted without ever seeing them, and how many
    // trimmed ranges that took. Recovery domain only.
    uint64_t forgiven_bytes = 0;
    uint32_t forgiven_ranges = 0;
    // The subset of forgiven_bytes the receiver never waited for at all,
    // because the flow went quiet with data still unsent. Trimmed-forgiven
    // bytes are the difference, derived rather than counted.
    uint64_t forgiven_remainder_bytes = 0;
    // Trims the cap could have afforded and the pacing coin declined anyway.
    // Nothing else can see them: a cap refusal is allowance_spent_signalled,
    // and a coin refusal leaves the cap untouched.
    uint32_t pacing_refusals = 0;
    // Congestion-exempt domain only. `cc_exempt` records the answer the
    // transport got at queue-pair creation and is never withdrawn: the flow's
    // exemption ended, but it was granted, and the telemetry is the record of
    // that. `allowance_spent_signalled` counts the receiver's reports that the
    // budget entry was spent, and `cc_rearmed_ns` is when one of them ended the
    // exemption; zero means none did.
    bool cc_exempt = false;
    uint32_t cc_signal_withheld = 0;
    uint32_t allowance_spent_signalled = 0;
    uint64_t cc_rearmed_ns = 0;
    // Zero means never; no packet can be trimmed or repaired at time zero.
    uint64_t first_trim_ns = 0;
    uint64_t first_repair_ns = 0;
    uint64_t start_time_ns = 0;
    uint64_t end_time_ns = 0;
    FlowTerminalOutcome terminal_outcome = FlowTerminalOutcome::Pending;
    std::string failure_reason;
};

inline ExperimentConfig experiment_config;
inline ForgivenessLedger forgiveness_ledger;

// Offered minus forgiven. A completed queue pair in the recovery domain
// delivered fewer bytes than it offered, by exactly the forgiven count;
// physical_bytes stays the offered figure so it keeps joining fct.txt and
// keeps denominating W. The telemetry column and the vesting charge are the
// same quantity, so they are the same function.
inline uint64_t delivered_bytes(const FlowRecord& flow) {
    return flow.physical_bytes >= flow.forgiven_bytes
        ? flow.physical_bytes - flow.forgiven_bytes
        : 0;
}

class ExperimentTelemetry {
  public:
    void initialize(const std::filesystem::path& output_dir) {
        std::filesystem::create_directories(output_dir);
        flow_events.open(output_dir / "flow_events.csv", std::ios::trunc);
        rank_completion.open(output_dir / "rank_completion.csv", std::ios::trunc);
        collective_events.open(output_dir / "collective_events.csv", std::ios::trunc);
        if (!flow_events || !rank_completion || !collective_events) {
            throw std::runtime_error("Unable to create experiment telemetry files");
        }
        flow_events
            << "flow_kind,decision,admission_eligible,parallelism_domain,"
               "origin_transport_role,transport_role,"
               "collective_type,training_step,workload_node_id,"
               "message_sequence,src,dst,tag,source_port,priority_group,"
               "logical_bytes,physical_bytes,data_attempted_bytes,"
               "retransmitted_bytes,trimmed_payload_bytes,recovery_events,"
               "trim_notifications,trim_lasthop_notifications,"
               "trim_recovery_events,stale_trim_notifications,terminal_outcome,"
               "failure_reason,decision_hash,start_time_ns,end_time_ns,"
               "timeouts,cnp_received,first_trim_ns,first_repair_ns,"
               "forgiven_bytes,forgiven_ranges,forgiven_remainder_bytes,"
               "pacing_refusals,delivered_bytes,cc_exempt,"
               "cc_signal_withheld,allowance_spent_signalled,"
               "cc_rearmed_ns\n";
        rank_completion << "rank,completion_time_ns\n";
        collective_events
            << "rank,parallelism_domain,collective_type,training_step,"
               "workload_node_id,logical_bytes,start_time_ns,end_time_ns\n";
    }

    bool enabled() const {
        return flow_events.is_open();
    }

    void record_flow(const FlowRecord& flow) {
        if (!enabled()) {
            return;
        }
        flow_events << flow_kind_name(flow.kind) << ','
                    << (flow.shed ? "shed" : "admitted") << ','
                    << (flow.admission_eligible ? "true" : "false") << ','
                    << parallelism_domain_name(flow.operation.parallelism_domain)
                    << ',' << transport_role_name(flow.origin_transport_role)
                    << ',' << transport_role_name(flow.operation.transport_role)
                    << ',' << collective_type_name(flow.operation.collective_type)
                    << ',' << flow.operation.training_step << ','
                    << flow.operation.workload_node_id << ','
                    << flow.operation.message_sequence << ',' << flow.src << ','
                    << flow.dst << ',' << flow.tag << ',' << flow.source_port
                    << ',' << flow.priority_group << ',' << flow.logical_bytes
                    << ',' << flow.physical_bytes << ','
                    << flow.data_attempted_bytes << ','
                    << flow.retransmitted_bytes << ','
                    << flow.trimmed_payload_bytes << ',' << flow.recovery_events
                    << ',' << flow.trim_notifications << ','
                    << flow.trim_lasthop_notifications << ','
                    << flow.trim_recovery_events << ','
                    << flow.stale_trim_notifications
                    << ',' << terminal_outcome_name(flow.terminal_outcome)
                    << ',' << flow.failure_reason << ',' << flow.decision_hash
                    << ',' << flow.start_time_ns << ',' << flow.end_time_ns
                    << ',' << flow.timeouts << ',' << flow.cnp_received << ','
                    << flow.first_trim_ns << ',' << flow.first_repair_ns << ','
                    << flow.forgiven_bytes << ',' << flow.forgiven_ranges
                    << ',' << flow.forgiven_remainder_bytes << ','
                    << flow.pacing_refusals << ',' << delivered_bytes(flow)
                    << ','
                    << (flow.cc_exempt ? "true" : "false") << ','
                    << flow.cc_signal_withheld << ','
                    << flow.allowance_spent_signalled << ','
                    << flow.cc_rearmed_ns << '\n';
    }

    void record_collective_completion(
        int rank,
        const AstraSim::OperationContext& operation,
        uint64_t logical_bytes,
        uint64_t start_time_ns,
        uint64_t end_time_ns) {
        if (!collective_events.is_open()) {
            return;
        }
        if (end_time_ns < start_time_ns) {
            throw std::runtime_error("collective completion precedes its start time");
        }
        // The rank has accounted for this step's DP All-Reduce, so its budget
        // for the step is spent whether or not it was used. A trim arriving
        // after this can only be pulled.
        if (rank >= 0 && AstraSim::is_dp_all_reduce_payload(operation)) {
            forgiveness_ledger.close(static_cast<uint32_t>(rank),
                                     operation.training_step);
        }
        collective_events << rank << ','
                          << parallelism_domain_name(operation.parallelism_domain)
                          << ',' << collective_type_name(operation.collective_type)
                          << ',' << operation.training_step << ','
                          << operation.workload_node_id << ',' << logical_bytes
                          << ',' << start_time_ns << ',' << end_time_ns << '\n';
    }

    void record_rank_completion(int rank, uint64_t completion_time_ns) {
        if (rank_completion.is_open()) {
            rank_completion << rank << ',' << completion_time_ns << '\n';
        }
    }

    void flush() {
        if (flow_events.is_open()) {
            flow_events.flush();
        }
        if (rank_completion.is_open()) {
            rank_completion.flush();
        }
        if (collective_events.is_open()) {
            collective_events.flush();
        }
    }

  private:
    static const char* flow_kind_name(FlowKind kind) {
        switch (kind) {
        case FlowKind::ForegroundPayload:
            return "foreground_payload";
        case FlowKind::ProvenanceControl:
            return "provenance_control";
        case FlowKind::BackgroundMicroburst:
            return "background_microburst";
        }
        return "unknown";
    }

    static const char* terminal_outcome_name(FlowTerminalOutcome outcome) {
        switch (outcome) {
        case FlowTerminalOutcome::Pending:
            return "pending";
        case FlowTerminalOutcome::Completed:
            return "completed";
        case FlowTerminalOutcome::Failed:
            return "failed";
        }
        return "unknown";
    }

    static const char* parallelism_domain_name(
        AstraSim::ParallelismDomain domain) {
        switch (domain) {
        case AstraSim::ParallelismDomain::Tensor:
            return "tp";
        case AstraSim::ParallelismDomain::Pipeline:
            return "pp";
        case AstraSim::ParallelismDomain::Data:
            return "dp";
        case AstraSim::ParallelismDomain::Unknown:
            return "unknown";
        }
        return "unknown";
    }

    static const char* transport_role_name(AstraSim::TransportRole role) {
        switch (role) {
        case AstraSim::TransportRole::CollectivePayload:
            return "collective_payload";
        case AstraSim::TransportRole::PointToPointPayload:
            return "point_to_point_payload";
        case AstraSim::TransportRole::RendezvousControl:
            return "rendezvous_control";
        case AstraSim::TransportRole::ProvenanceControl:
            return "provenance_control";
        case AstraSim::TransportRole::BackgroundTraffic:
            return "background_traffic";
        case AstraSim::TransportRole::Unknown:
            return "unknown";
        }
        return "unknown";
    }

    static const char* collective_type_name(AstraSim::ComType type) {
        switch (type) {
        case AstraSim::ComType::All_Reduce:
            return "all_reduce";
        case AstraSim::ComType::All_to_All:
            return "all_to_all";
        case AstraSim::ComType::All_Gather:
            return "all_gather";
        case AstraSim::ComType::Reduce_Scatter:
            return "reduce_scatter";
        case AstraSim::ComType::All_Reduce_All_to_All:
            return "all_reduce_all_to_all";
        case AstraSim::ComType::None:
            return "none";
        }
        return "unknown";
    }

    std::ofstream flow_events;
    std::ofstream rank_completion;
    std::ofstream collective_events;
};

inline ExperimentTelemetry experiment_telemetry;

inline void validate_priority_group(uint16_t priority_group,
                                    const std::string& field_name) {
    if (priority_group >= kPriorityGroupCount) {
        throw std::runtime_error(field_name + " must be in [0, 7]");
    }
}

inline uint64_t stable_operation_hash(const AstraSim::sim_request& request,
                                      int src,
                                      int dst,
                                      int tag) {
    uint64_t hash = experiment_config.seed;
    hash_combine(hash, request.operation.training_step);
    hash_combine(hash, request.operation.workload_node_id);
    hash_combine(hash, request.operation.message_sequence);
    hash_combine(hash, static_cast<uint64_t>(src));
    hash_combine(hash, static_cast<uint64_t>(dst));
    hash_combine(hash, static_cast<uint64_t>(tag));
    return hash;
}

inline SheddingDecision evaluate_shedding(const AstraSim::sim_request& request,
                                          int src,
                                          int dst,
                                          int tag) {
    SheddingDecision decision;
    if (!experiment_config.enabled ||
        !AstraSim::is_dp_all_reduce_payload(request.operation)) {
        return decision;
    }

    decision.eligible = true;
    // Before the domain branch: the hash identifies the operation, not the
    // decision taken on it, and every arm's flow_events.csv is joined on it.
    // Computing it only on the admission path left recovery rows carrying
    // zero, so a join across arms differed for a reason that is not the
    // domain.
    decision.decision_hash = stable_operation_hash(request, src, dst, tag);
    // The recovery domain spends the same budget after a trim, so shedding at
    // admission as well would double-spend it. Eligibility is still recorded:
    // it is what makes a flow forgivable later, and it keeps the two domains'
    // eligible populations identical for a matched comparison.
    if (forgives(experiment_config.domain)) {
        return decision;
    }
    if (experiment_config.clr_mask_configured) {
        const auto clr = experiment_config.clr_mask_by_step.find(
            request.operation.training_step);
        if (clr == experiment_config.clr_mask_by_step.end()) {
            throw std::runtime_error(
                "CLR mask does not define the request training step");
        }
        decision.is_clr = clr->second;
        const uint64_t threshold = decision.is_clr
            ? experiment_config.p_low_threshold
            : experiment_config.p_high_threshold;
        decision.shed = decision.decision_hash % kDecisionScale < threshold;
        return decision;
    }
    const auto threshold = experiment_config.shedding_threshold_by_step.find(
        request.operation.training_step);
    if (threshold == experiment_config.shedding_threshold_by_step.end()) {
        return decision;
    }
    decision.shed =
        decision.decision_hash % kDecisionScale < threshold->second;
    return decision;
}

// The step's threshold, and zero when the mask does not define the step. Zero
// is free as that sentinel because the parser refuses a p_low of zero and
// p_high is never below it. Both verdict shells and the closing check resolve
// the threshold the same way, so they resolve it through the same function.
inline uint64_t step_threshold(uint32_t step) {
    const auto clr = experiment_config.clr_mask_by_step.find(step);
    if (clr == experiment_config.clr_mask_by_step.end()) {
        return 0;
    }
    return clr->second ? experiment_config.p_low_threshold
                       : experiment_config.p_high_threshold;
}

inline uint64_t step_threshold(const FlowRecord& flow) {
    return step_threshold(flow.operation.training_step);
}

// The contract, asserted where a cell stops changing: the receiving rank kept
// at least 1 - p(step) of what the step owed it. `affords` makes the throw
// unreachable, since eligible only grows and every charge was measured
// against it; the throw is what stops a later change to `affords`, to the
// remainder path, or to the ledger from shipping a run that broke the
// contract.
//
// close resolves the threshold rather than receiving one, because a caller
// that supplied it could measure a cell against a budget the cell was never
// charged under, and because the two-argument call keeps close total in what
// a caller knows: a rank and a step name a cell or they name nothing, and
// naming nothing closes nothing. A step the mask does not define resolves to
// zero, which is the budget its verdicts already used, so a cell that spent
// nothing under it closes and one that spent anything throws.
inline void ForgivenessLedger::close(uint32_t dst, uint32_t step) {
    StepLedger* cell = find(dst, step);
    if (cell == nullptr) {
        return;
    }
    const uint64_t threshold = step_threshold(step);
    const uint64_t spent = cell->shed + cell->forgiven;
    if (spent * kDecisionScale > cell->eligible * threshold) {
        throw std::runtime_error(
            "forgiveness ledger broke the budget law at rank " +
            std::to_string(dst) + " step " + std::to_string(step) +
            ": eligible " + std::to_string(cell->eligible) + " B, shed " +
            std::to_string(cell->shed) + " B, forgiven " +
            std::to_string(cell->forgiven) + " B, threshold " +
            std::to_string(threshold) + " of " +
            std::to_string(kDecisionScale));
    }
    cell->closed = true;
}

// Whether the experiment layer may answer a receiver's question about this
// flow at all. Shared by both verdicts, because both ask the same thing of
// the flow; the exemption asks a narrower one and keeps its own guard.
inline bool forgivable(const FlowRecord& flow) {
    return experiment_config.enabled && forgives(experiment_config.domain) &&
           flow.kind == FlowKind::ForegroundPayload && flow.admission_eligible;
}

// The trim verdict the transport asks for. The transport is semantics-blind:
// it supplies a flow, a range start and a byte count, and learns nothing
// about steps, phases, or budgets. A thin shell over trim_verdict: it
// eliminates the cell, draws the coin, stores the answer back, and counts.
//
// The allowance bit rides on whatever the answer is, because a sender cannot
// read a budget entry every other sender to that rank shares.
inline uint8_t evaluate_forgiveness(FlowRecord& flow,
                                    uint64_t start,
                                    uint64_t bytes) {
    if (!forgivable(flow)) {
        return 0;
    }
    const uint64_t threshold = step_threshold(flow);
    if (threshold == 0) {
        return 0;
    }
    StepLedger* cell = forgiveness_ledger.open_cell(
        static_cast<uint32_t>(flow.dst), flow.operation.training_step);
    if (cell == nullptr) {
        return 0;
    }
    const uint64_t coin = range_coin(flow.decision_hash, start);
    // Only a range the cap could still have afforded: that is the forgiveness
    // the coin cost, and it makes the two refusals decompose without overlap,
    // the cap's into allowance_spent_signalled and the coin's into this.
    if (paces_out(experiment_config.pacing, coin) &&
        affords(*cell, threshold, experiment_config.pacing, bytes)) {
        flow.pacing_refusals++;
    }
    const auto answer =
        trim_verdict(*cell, threshold, experiment_config.pacing, coin, bytes);
    *cell = answer.second;
    if (forgave(answer.first)) {
        flow.forgiven_bytes += bytes;
        flow.forgiven_ranges++;
    }
    return answer.first;
}

// The straggler stop. The receive queue pair knows how far its cumulative
// sequence has reached and how much arrived above it, and not how large the
// flow is; this knows the size. The hole is what is left, and the answer is
// the end offset to absorb, or zero to refuse.
//
// Under selective repeat a stalled flow keeps accepting packets past the gap,
// so `accepted_above` is usually nonzero and charging the whole span above the
// cumulative sequence would spend the budget on bytes the receiver holds.
//
// forgiven_ranges stays untouched: it counts the trims a forgiveness spared a
// repair, and a remainder was never trimmed. That keeps one rate cut per trim
// as the identity a fixture can assert.
inline uint64_t evaluate_remainder(FlowRecord& flow,
                                   uint64_t next_expected,
                                   uint64_t accepted_above) {
    if (!forgivable(flow) ||
        flow.physical_bytes < next_expected + accepted_above) {
        return 0;
    }
    const uint64_t remainder =
        flow.physical_bytes - next_expected - accepted_above;
    const uint64_t threshold = step_threshold(flow);
    if (remainder == 0 || threshold == 0) {
        return 0;
    }
    StepLedger* cell = forgiveness_ledger.open_cell(
        static_cast<uint32_t>(flow.dst), flow.operation.training_step);
    if (cell == nullptr) {
        return 0;
    }
    const auto answer = remainder_verdict(*cell, threshold,
                                          experiment_config.pacing, remainder);
    *cell = answer.second;
    if (answer.first == 0) {
        return 0;
    }
    flow.forgiven_bytes += answer.first;
    flow.forgiven_remainder_bytes += answer.first;
    return flow.physical_bytes;
}

// Whether one queue pair may ignore congestion signals for as long as the
// receiver keeps forgiving its trims. Asked once, at creation, and total: an
// unknown step, a critical step, or a budget already spent all answer false,
// which is the congestion response of a transport without this domain. It
// spends no budget; only forgiving does. The only mutation is the flow's own
// record of the answer.
inline bool evaluate_congestion_exemption(FlowRecord& flow) {
    if (!experiment_config.enabled ||
        experiment_config.domain != SheddingDomain::RecoveryExempt ||
        flow.kind != FlowKind::ForegroundPayload || !flow.admission_eligible) {
        return false;
    }
    const uint32_t step = flow.operation.training_step;
    const auto clr = experiment_config.clr_mask_by_step.find(step);
    // A critical step obeys congestion control: its budget is the strict one
    // and the exemption is not part of what it buys.
    if (clr == experiment_config.clr_mask_by_step.end() || clr->second) {
        return false;
    }
    const StepLedger* cell =
        forgiveness_ledger.open_cell(static_cast<uint32_t>(flow.dst), step);
    if (cell == nullptr ||
        !affords(*cell, experiment_config.p_high_threshold,
                 experiment_config.pacing, 0)) {
        return false;
    }
    flow.cc_exempt = true;
    return true;
}

inline uint16_t priority_group_for_vnet(uint32_t vnet) {
    const auto mapping = experiment_config.vnet_to_priority_group.find(vnet);
    if (mapping != experiment_config.vnet_to_priority_group.end()) {
        return mapping->second;
    }
    return experiment_config.default_priority_group;
}

inline void reject_unknown_keys(const nlohmann::json& value,
                                std::initializer_list<const char*> allowed,
                                const std::string& object_name) {
    for (auto it = value.begin(); it != value.end(); ++it) {
        const auto allowed_key = std::find_if(
            allowed.begin(), allowed.end(), [&](const char* key) {
                return it.key() == key;
            });
        if (allowed_key == allowed.end()) {
            throw std::runtime_error("Unknown key '" + it.key() + "' in " +
                                     object_name);
        }
    }
}

inline uint64_t parse_uint64_key(const std::string& value,
                                 const std::string& field_name) {
    size_t consumed = 0;
    uint64_t result = 0;
    try {
        result = std::stoull(value, &consumed);
    } catch (const std::exception&) {
        throw std::runtime_error(field_name + " key must be an unsigned integer");
    }
    if (consumed != value.size()) {
        throw std::runtime_error(field_name + " key must be an unsigned integer");
    }
    return result;
}

inline uint16_t parse_priority_group(const nlohmann::json& value,
                                     const std::string& field_name) {
    if (!value.is_number_unsigned() ||
        value.get<uint64_t>() >= kPriorityGroupCount) {
        throw std::runtime_error(field_name + " must be an integer in [0, 7]");
    }
    return static_cast<uint16_t>(value.get<uint64_t>());
}

inline uint64_t parse_probability_threshold(const nlohmann::json& value,
                                            const std::string& field_name) {
    if (!value.is_number()) {
        throw std::runtime_error(field_name + " must be a number in [0, 1]");
    }
    const double probability = value.get<double>();
    if (!std::isfinite(probability) || probability < 0.0 || probability > 1.0) {
        throw std::runtime_error(field_name + " must be a number in [0, 1]");
    }
    return static_cast<uint64_t>(
        std::llround(probability * static_cast<double>(kDecisionScale)));
}

// The generator writes the scaled integer beside the float it came from.
// Both are optional for a hand-written file, but a present one must agree
// with llround of the float, which is what the simulator itself rounds to.
inline void require_scaled_threshold(const nlohmann::json& policy,
                                     const char* key,
                                     uint64_t rounded) {
    if (!policy.contains(key)) {
        return;
    }
    const auto& value = policy.at(key);
    if (!value.is_number_unsigned() || value.get<uint64_t>() > kDecisionScale) {
        throw std::runtime_error(
            std::string("selection_policy.") + key +
            " must be an unsigned integer in [0, 1000000]");
    }
    if (value.get<uint64_t>() != rounded) {
        throw std::runtime_error(
            std::string("selection_policy.") + key + " is " +
            std::to_string(value.get<uint64_t>()) + " but the probability "
            "beside it rounds to " + std::to_string(rounded));
    }
}

// The one smart constructor for the pacing rule. A probability outside the
// open interval is not a pacing rule: zero forgives nothing, which is the
// admission domain, and one declines nothing, which is no pacing. A
// probability beside any other kind is a value that would be read by nothing.
inline void parse_pacing(const nlohmann::json& policy) {
    if (!policy.contains("pacing")) {
        return;
    }
    const auto& pacing = policy.at("pacing");
    if (!pacing.is_object()) {
        throw std::runtime_error("selection_policy.pacing must be an object");
    }
    reject_unknown_keys(pacing, {"kind", "p"}, "selection_policy.pacing");
    if (!pacing.contains("kind") || !pacing.at("kind").is_string()) {
        throw std::runtime_error("selection_policy.pacing requires kind");
    }
    const std::string kind = pacing.at("kind").get<std::string>();
    if (kind == "bernoulli") {
        if (!pacing.contains("p")) {
            throw std::runtime_error(
                "selection_policy.pacing kind 'bernoulli' requires p");
        }
        const uint64_t threshold = parse_probability_threshold(
            pacing.at("p"), "selection_policy.pacing.p");
        if (threshold == 0 || threshold >= kDecisionScale) {
            throw std::runtime_error(
                "selection_policy.pacing.p must be strictly between 0 and 1");
        }
        experiment_config.pacing = Bernoulli{threshold};
        return;
    }
    if (pacing.contains("p")) {
        throw std::runtime_error(
            "selection_policy.pacing.p belongs to kind 'bernoulli' alone");
    }
    if (kind == "none") {
        experiment_config.pacing = NoPacing{};
        return;
    }
    if (kind == "vesting") {
        experiment_config.pacing = Vesting{};
        return;
    }
    throw std::runtime_error(
        "selection_policy.pacing.kind must be none, bernoulli, or vesting");
}

// Absent disables the straggler stop; zero enables it and asks at every
// arrival, which is stop-at-(1-p) as the degenerate point of this rule.
inline void parse_straggler_idle(const nlohmann::json& policy) {
    if (!policy.contains("straggler_idle_ns")) {
        return;
    }
    const auto& idle = policy.at("straggler_idle_ns");
    if (!idle.is_number_unsigned()) {
        throw std::runtime_error(
            "selection_policy.straggler_idle_ns must be a nonnegative integer");
    }
    experiment_config.straggler_idle_ns = idle.get<uint64_t>();
}

inline void configure_clr_mask(const std::string& configuration_path) {
    if (configuration_path.empty() || configuration_path == "empty") {
        return;
    }
    if (!experiment_config.enabled) {
        throw std::runtime_error(
            "--clr-mask-configuration requires an enabled experiment");
    }
    if (!experiment_config.selection_policy_configured) {
        throw std::runtime_error(
            "--clr-mask-configuration requires selection_policy in the experiment configuration");
    }

    std::ifstream input(configuration_path);
    if (!input) {
        throw std::runtime_error("Unable to open CLR mask: " + configuration_path);
    }
    std::string line;
    if (!std::getline(input, line)) {
        throw std::runtime_error("CLR mask must contain a header");
    }
    if (!line.empty() && line.back() == '\r') {
        line.pop_back();
    }
    if (line != "step_id,is_clr,probability") {
        throw std::runtime_error(
            "CLR mask header must be step_id,is_clr,probability");
    }

    uint64_t row_count = 0;
    while (std::getline(input, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        if (line.empty()) {
            throw std::runtime_error("CLR mask must not contain blank rows");
        }
        std::stringstream stream(line);
        std::string step_text;
        std::string clr_text;
        std::string probability_text;
        std::string unexpected;
        if (!std::getline(stream, step_text, ',') ||
            !std::getline(stream, clr_text, ',') ||
            !std::getline(stream, probability_text, ',') ||
            std::getline(stream, unexpected, ',')) {
            throw std::runtime_error(
                "CLR mask rows must contain step_id,is_clr,probability");
        }
        const uint64_t step = parse_uint64_key(step_text, "CLR mask step_id");
        if (step == 0 || step > std::numeric_limits<uint32_t>::max()) {
            throw std::runtime_error("CLR mask step_id must be a nonzero uint32");
        }
        if (clr_text != "0" && clr_text != "1") {
            throw std::runtime_error("CLR mask is_clr must be 0 or 1");
        }
        size_t probability_length = 0;
        double probability = 0.0;
        try {
            probability = std::stod(probability_text, &probability_length);
        } catch (const std::exception&) {
            throw std::runtime_error("CLR mask probability must be in [0, 1]");
        }
        if (probability_length != probability_text.size() ||
            !std::isfinite(probability) || probability < 0.0 ||
            probability > 1.0) {
            throw std::runtime_error("CLR mask probability must be in [0, 1]");
        }
        if (!experiment_config.clr_mask_by_step
                 .emplace(static_cast<uint32_t>(step), clr_text == "1")
                 .second) {
            throw std::runtime_error("CLR mask must not contain duplicate step_id values");
        }
        ++row_count;
    }
    if (row_count == 0) {
        throw std::runtime_error("CLR mask must contain at least one step");
    }
    experiment_config.clr_mask_configured = true;
}

inline void configure_experiment(const std::string& configuration_path,
                                 const std::string& output_dir) {
    experiment_config = ExperimentConfig{};
    forgiveness_ledger = ForgivenessLedger{};
    if (configuration_path.empty() || configuration_path == "empty") {
        return;
    }
    if (output_dir.empty() || output_dir == "empty") {
        throw std::runtime_error(
            "--experiment-output-dir is required with --experiment-configuration");
    }

    std::ifstream input(configuration_path);
    if (!input) {
        throw std::runtime_error("Unable to open experiment configuration: " +
                                 configuration_path);
    }

    nlohmann::json root;
    input >> root;
    if (!root.is_object()) {
        throw std::runtime_error("Experiment configuration must be a JSON object");
    }
    reject_unknown_keys(root,
                        {"schema_version", "enabled", "seed", "run_id",
                         "eligibility", "selection_probability_by_step",
                         "selection_policy", "scale",
                         "default_priority_group", "provenance",
                         "vnet_to_priority_group", "microburst"},
                        "experiment configuration");
    if (root.value("schema_version", 0) != 1) {
        throw std::runtime_error("Experiment schema_version must be 1");
    }
    if (!root.contains("enabled") || !root.at("enabled").is_boolean()) {
        throw std::runtime_error("Experiment configuration requires boolean enabled");
    }

    experiment_config.enabled = root.at("enabled").get<bool>();
    if (root.contains("seed")) {
        if (!root.at("seed").is_number_unsigned()) {
            throw std::runtime_error("seed must be an unsigned integer");
        }
        experiment_config.seed = root.at("seed").get<uint64_t>();
    }
    if (root.contains("run_id")) {
        if (!root.at("run_id").is_string()) {
            throw std::runtime_error("run_id must be a string");
        }
        experiment_config.run_id = root.at("run_id").get<std::string>();
    }

    if (experiment_config.enabled) {
        if (!root.contains("eligibility") ||
            root.at("eligibility") != "dp_all_reduce_only") {
            throw std::runtime_error(
                "enabled experiments require eligibility=dp_all_reduce_only");
        }
    }

    if (root.contains("default_priority_group")) {
        experiment_config.default_priority_group = parse_priority_group(
            root.at("default_priority_group"), "default_priority_group");
    }

    if (root.contains("provenance")) {
        const auto& provenance = root.at("provenance");
        if (!provenance.is_object()) {
            throw std::runtime_error("provenance must be an object");
        }
        reject_unknown_keys(provenance, {"control_bytes", "priority_group"},
                            "provenance");
        if (provenance.contains("control_bytes")) {
            if (!provenance.at("control_bytes").is_number_unsigned() ||
                provenance.at("control_bytes").get<uint64_t>() == 0) {
                throw std::runtime_error(
                    "provenance.control_bytes must be a nonzero unsigned integer");
            }
            experiment_config.provenance_control_bytes =
                provenance.at("control_bytes").get<uint64_t>();
        }
        if (provenance.contains("priority_group")) {
            experiment_config.provenance_priority_group = parse_priority_group(
                provenance.at("priority_group"), "provenance.priority_group");
        }
        if (experiment_config.provenance_priority_group == 0) {
            throw std::runtime_error(
                "provenance.priority_group must reserve priority group 0");
        }
    }

    if (root.contains("vnet_to_priority_group")) {
        const auto& mappings = root.at("vnet_to_priority_group");
        if (!mappings.is_object()) {
            throw std::runtime_error("vnet_to_priority_group must be an object");
        }
        for (auto it = mappings.begin(); it != mappings.end(); ++it) {
            const auto vnet = parse_uint64_key(it.key(), "vnet_to_priority_group");
            if (vnet > std::numeric_limits<uint32_t>::max()) {
                throw std::runtime_error("vnet_to_priority_group key exceeds uint32");
            }
            experiment_config.vnet_to_priority_group.emplace(
                static_cast<uint32_t>(vnet),
                parse_priority_group(it.value(),
                                     "vnet_to_priority_group priority group"));
        }
    }

    if (root.contains("selection_probability_by_step")) {
        const auto& probabilities = root.at("selection_probability_by_step");
        if (!probabilities.is_object()) {
            throw std::runtime_error(
                "selection_probability_by_step must be an object");
        }
        for (auto it = probabilities.begin(); it != probabilities.end(); ++it) {
            const auto step = parse_uint64_key(
                it.key(), "selection_probability_by_step");
            if (step == 0 || step > std::numeric_limits<uint32_t>::max()) {
                throw std::runtime_error(
                    "selection_probability_by_step keys must be nonzero uint32 values");
            }
            experiment_config.shedding_threshold_by_step.emplace(
                static_cast<uint32_t>(step),
                parse_probability_threshold(
                    it.value(), "selection_probability_by_step probability"));
        }
    }

    if (root.contains("selection_policy")) {
        const auto& policy = root.at("selection_policy");
        if (!policy.is_object()) {
            throw std::runtime_error("selection_policy must be an object");
        }
        reject_unknown_keys(policy,
                            {"semantics", "p_low", "p_high", "p_low_threshold",
                             "p_high_threshold", "domain", "transport",
                             "pacing", "straggler_idle_ns"},
                            "selection_policy");
        if (policy.contains("domain")) {
            const auto& domain = policy.at("domain");
            if (domain == "admission") {
                experiment_config.domain = SheddingDomain::Admission;
            } else if (domain == "recovery") {
                experiment_config.domain = SheddingDomain::Recovery;
            } else if (domain == "recovery_exempt") {
                experiment_config.domain = SheddingDomain::RecoveryExempt;
            } else {
                throw std::runtime_error(
                    "selection_policy.domain must be admission, recovery, or "
                    "recovery_exempt");
            }
        }
        const char* expected_semantics =
            selection_semantics(experiment_config.domain);
        if (!policy.contains("semantics") ||
            policy.at("semantics") != expected_semantics) {
            throw std::runtime_error(
                std::string("selection_policy.semantics must be ") +
                expected_semantics);
        }
        if (forgives(experiment_config.domain)) {
            // The frontend cannot read network_config.txt, so the generator
            // asserts the transport contract here and entry.h checks the
            // assertion against the transport ns-3 actually built. Recovery
            // needs both: without ftd trimming nothing reaches the receiver to
            // forgive, and without selective repair the receiver never
            // consults the out-of-order range a forgiven hole becomes.
            if (!policy.contains("transport")) {
                throw std::runtime_error(
                    "recovery domain requires selection_policy.transport");
            }
            const auto& transport = policy.at("transport");
            if (!transport.is_object()) {
                throw std::runtime_error(
                    "selection_policy.transport must be an object");
            }
            reject_unknown_keys(transport,
                                {"selective_repair", "packet_trimming_ftd"},
                                "selection_policy.transport");
            for (const char* key : {"selective_repair", "packet_trimming_ftd"}) {
                if (!transport.contains(key) ||
                    !transport.at(key).is_boolean() ||
                    !transport.at(key).get<bool>()) {
                    throw std::runtime_error(
                        std::string("recovery domain requires "
                                    "selection_policy.transport.") + key);
                }
            }
        }
        for (const char* key : {"p_low", "p_high"}) {
            if (!policy.contains(key)) {
                throw std::runtime_error(
                    std::string("selection_policy requires ") + key);
            }
        }
        experiment_config.p_low_threshold = parse_probability_threshold(
            policy.at("p_low"), "selection_policy.p_low");
        experiment_config.p_high_threshold = parse_probability_threshold(
            policy.at("p_high"), "selection_policy.p_high");
        // The budget law is integer arithmetic on these thresholds, and the
        // analyzer checks the same law from the same integers in the file.
        // Refusing a disagreement is what keeps one law in two languages from
        // becoming two laws: a boundary cell must not be spent here and
        // reported violated there.
        require_scaled_threshold(policy, "p_low_threshold",
                                 experiment_config.p_low_threshold);
        require_scaled_threshold(policy, "p_high_threshold",
                                 experiment_config.p_high_threshold);
        // The strict-CLR ceiling on p_low (<= 0.01) is experiment-design
        // policy owned by the generator, which grants exactly one documented
        // exemption: the fixed-high comparison arm runs with p_low set to
        // the permissive rate. The simulator enforces only representability;
        // re-imposing the ceiling here rejected every fixed-high arm.
        if (experiment_config.p_low_threshold == 0) {
            throw std::runtime_error(
                "selection_policy.p_low must be greater than zero");
        }
        if (experiment_config.p_low_threshold >
            experiment_config.p_high_threshold) {
            throw std::runtime_error(
                "selection_policy.p_high must be at least p_low");
        }
        // Both v2 policies belong to the receiver, and only a forgiving
        // domain has a receiver that decides anything.
        if (!forgives(experiment_config.domain)) {
            for (const char* key : {"pacing", "straggler_idle_ns"}) {
                if (policy.contains(key)) {
                    throw std::runtime_error(
                        std::string("selection_policy.") + key +
                        " requires a forgiving domain");
                }
            }
        }
        parse_pacing(policy);
        parse_straggler_idle(policy);
        experiment_config.selection_policy_configured = true;
    }

    if (root.contains("scale")) {
        const auto& scale = root.at("scale");
        if (!scale.is_object()) {
            throw std::runtime_error("scale must be an object");
        }
        reject_unknown_keys(scale, {"ranks", "steps"}, "scale");
        for (const char* key : {"ranks", "steps"}) {
            if (!scale.contains(key) || !scale.at(key).is_number_unsigned() ||
                scale.at(key).get<uint64_t>() == 0 ||
                scale.at(key).get<uint64_t>() >
                    std::numeric_limits<uint32_t>::max()) {
                throw std::runtime_error(
                    std::string("scale.") + key + " must be a nonzero uint32");
            }
        }
        experiment_config.rank_count =
            static_cast<uint32_t>(scale.at("ranks").get<uint64_t>());
        experiment_config.step_count =
            static_cast<uint32_t>(scale.at("steps").get<uint64_t>());
    }
    if (forgives(experiment_config.domain)) {
        if (experiment_config.rank_count == 0 ||
            experiment_config.step_count == 0) {
            throw std::runtime_error("recovery domain requires scale");
        }
        forgiveness_ledger = ForgivenessLedger::make(
            experiment_config.rank_count, experiment_config.step_count);
    }

    if (root.contains("microburst")) {
        const auto& microburst = root.at("microburst");
        if (!microburst.is_object()) {
            throw std::runtime_error("microburst must be an object");
        }
        reject_unknown_keys(microburst, {"enabled", "trigger_step", "flows"},
                            "microburst");
        if (!microburst.contains("enabled") ||
            !microburst.at("enabled").is_boolean()) {
            throw std::runtime_error("microburst.enabled must be a boolean");
        }
        experiment_config.microburst_enabled =
            microburst.at("enabled").get<bool>();
        if (microburst.contains("trigger_step")) {
            if (!microburst.at("trigger_step").is_number_unsigned() ||
                microburst.at("trigger_step").get<uint64_t>() == 0 ||
                microburst.at("trigger_step").get<uint64_t>() >
                    std::numeric_limits<uint32_t>::max()) {
                throw std::runtime_error(
                    "microburst.trigger_step must be a nonzero uint32");
            }
            experiment_config.microburst_trigger_step = static_cast<uint32_t>(
                microburst.at("trigger_step").get<uint64_t>());
        }
        if (experiment_config.microburst_enabled) {
            if (!microburst.contains("flows") || !microburst.at("flows").is_array() ||
                microburst.at("flows").empty()) {
                throw std::runtime_error(
                    "enabled microburst requires a nonempty flows array");
            }
            for (const auto& flow : microburst.at("flows")) {
                if (!flow.is_object()) {
                    throw std::runtime_error("microburst flow must be an object");
                }
                reject_unknown_keys(flow,
                                    {"src", "dst", "size_bytes", "offset_ns",
                                     "priority_group"},
                                    "microburst flow");
                for (const char* key : {"src", "dst", "size_bytes", "offset_ns"}) {
                    if (!flow.contains(key) || !flow.at(key).is_number_unsigned()) {
                        throw std::runtime_error(
                            std::string("microburst flow requires unsigned ") + key);
                    }
                }
                const uint64_t src = flow.at("src").get<uint64_t>();
                const uint64_t dst = flow.at("dst").get<uint64_t>();
                if (src > std::numeric_limits<uint32_t>::max() ||
                    dst > std::numeric_limits<uint32_t>::max() || src == dst ||
                    flow.at("size_bytes").get<uint64_t>() == 0) {
                    throw std::runtime_error(
                        "microburst flow requires distinct uint32 endpoints and nonzero size_bytes");
                }
                MicroburstFlow parsed_flow;
                parsed_flow.src = static_cast<uint32_t>(src);
                parsed_flow.dst = static_cast<uint32_t>(dst);
                parsed_flow.size_bytes = flow.at("size_bytes").get<uint64_t>();
                parsed_flow.offset_ns = flow.at("offset_ns").get<uint64_t>();
                parsed_flow.priority_group = flow.contains("priority_group")
                    ? parse_priority_group(flow.at("priority_group"),
                                           "microburst.priority_group")
                    : experiment_config.default_priority_group;
                experiment_config.microburst_flows.push_back(parsed_flow);
            }
        }
    }

    experiment_config.telemetry_output_dir = output_dir;
}

// Refusals the configuration alone cannot make, because the CLR mask arrives
// on its own command-line argument after the experiment is parsed. Run once,
// after both.
inline void validate_experiment_contract() {
    if (!experiment_config.enabled || !forgives(experiment_config.domain)) {
        return;
    }
    // Recovery reads the mask per trim and answers Pull for a step it does
    // not find. Without the mask the whole arm forgives nothing and reads as
    // "the mechanism did nothing", which is indistinguishable from a real
    // negative result. evaluate_shedding throws on the same miss, so the two
    // consumers of one map now refuse on the same terms.
    if (!experiment_config.clr_mask_configured) {
        throw std::runtime_error(
            "recovery domain requires --clr-mask-configuration");
    }
    for (uint32_t step = 1; step <= experiment_config.step_count; ++step) {
        if (experiment_config.clr_mask_by_step.count(step) == 0) {
            throw std::runtime_error(
                "CLR mask does not define training step " +
                std::to_string(step) + ", which the recovery domain requires");
        }
    }
}

// Opened only once ns-3 setup has succeeded. A refused arm must not leave a
// run directory carrying headers and no rows, which reads as started.
inline void open_experiment_telemetry() {
    if (!experiment_config.telemetry_output_dir.empty()) {
        experiment_telemetry.initialize(experiment_config.telemetry_output_dir);
    }
}

inline void finalize_experiment_telemetry() {
    experiment_telemetry.flush();
}

}  // namespace AstraSimNs3

#endif /* __ASTRA_SIM_NS3_EXPERIMENT_CONFIG_HH__ */
