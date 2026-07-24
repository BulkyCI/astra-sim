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
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <json/json.hpp>

namespace AstraSimNs3 {

constexpr uint64_t kDecisionScale = 1000000;
constexpr uint16_t kPriorityGroupCount = 8;

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
    uint64_t run_hash = 0;
    std::string run_id = "default";
    uint16_t default_priority_group = 3;
    uint16_t provenance_priority_group = 1;
    uint64_t provenance_control_bytes = 64;
    std::map<uint32_t, uint16_t> vnet_to_priority_group;
    std::map<uint32_t, uint64_t> shedding_threshold_by_step;
    bool clr_tolerances_configured = false;
    uint64_t clr_drop_threshold = 0;
    uint64_t stable_drop_threshold = 0;
    bool clr_mask_configured = false;
    std::map<uint32_t, bool> clr_mask_by_step;
    bool microburst_enabled = false;
    uint32_t microburst_trigger_step = 2;
    std::vector<MicroburstFlow> microburst_flows;
    bool microburst_triggered = false;
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
    uint32_t recovery_events = 0;
    uint64_t start_time_ns = 0;
    uint64_t end_time_ns = 0;
    FlowTerminalOutcome terminal_outcome = FlowTerminalOutcome::Pending;
    std::string failure_reason;
};

inline ExperimentConfig experiment_config;

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
               "retransmitted_bytes,recovery_events,terminal_outcome,"
               "failure_reason,decision_hash,start_time_ns,end_time_ns\n";
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
                    << flow.retransmitted_bytes << ',' << flow.recovery_events
                    << ',' << terminal_outcome_name(flow.terminal_outcome)
                    << ',' << flow.failure_reason << ',' << flow.decision_hash
                    << ',' << flow.start_time_ns << ',' << flow.end_time_ns
                    << '\n';
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

inline uint64_t stable_string_hash(const std::string& value) {
    uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char character : value) {
        hash ^= character;
        hash *= 1099511628211ULL;
    }
    return hash;
}

inline uint64_t mix_hash(uint64_t value) {
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31U);
}

inline void hash_combine(uint64_t& hash, uint64_t value) {
    hash = mix_hash(hash ^ mix_hash(value));
}

inline uint64_t stable_operation_hash(const AstraSim::sim_request& request,
                                      int src,
                                      int dst,
                                      int tag) {
    uint64_t hash = experiment_config.seed;
    hash_combine(hash, experiment_config.run_hash);
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
    decision.decision_hash = stable_operation_hash(request, src, dst, tag);
    if (experiment_config.clr_mask_configured) {
        const auto clr = experiment_config.clr_mask_by_step.find(
            request.operation.training_step);
        if (clr == experiment_config.clr_mask_by_step.end()) {
            throw std::runtime_error(
                "CLR mask does not define the request training step");
        }
        decision.is_clr = clr->second;
        const uint64_t threshold = decision.is_clr
            ? experiment_config.clr_drop_threshold
            : experiment_config.stable_drop_threshold;
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

inline void configure_clr_mask(const std::string& configuration_path) {
    if (configuration_path.empty() || configuration_path == "empty") {
        return;
    }
    if (!experiment_config.enabled) {
        throw std::runtime_error(
            "--clr-mask-configuration requires an enabled experiment");
    }
    if (!experiment_config.clr_tolerances_configured) {
        throw std::runtime_error(
            "--clr-mask-configuration requires clr_tolerances in the experiment configuration");
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
                         "eligibility", "drop_probability_by_step",
                         "clr_tolerances",
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
    experiment_config.run_hash = stable_string_hash(experiment_config.run_id);

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

    if (root.contains("drop_probability_by_step")) {
        const auto& probabilities = root.at("drop_probability_by_step");
        if (!probabilities.is_object()) {
            throw std::runtime_error("drop_probability_by_step must be an object");
        }
        for (auto it = probabilities.begin(); it != probabilities.end(); ++it) {
            const auto step = parse_uint64_key(it.key(), "drop_probability_by_step");
            if (step == 0 || step > std::numeric_limits<uint32_t>::max()) {
                throw std::runtime_error(
                    "drop_probability_by_step keys must be nonzero uint32 values");
            }
            experiment_config.shedding_threshold_by_step.emplace(
                static_cast<uint32_t>(step),
                parse_probability_threshold(
                    it.value(), "drop_probability_by_step probability"));
        }
    }

    if (root.contains("clr_tolerances")) {
        const auto& tolerances = root.at("clr_tolerances");
        if (!tolerances.is_object()) {
            throw std::runtime_error("clr_tolerances must be an object");
        }
        reject_unknown_keys(tolerances,
                            {"clr_drop_probability",
                             "stable_drop_probability"},
                            "clr_tolerances");
        for (const char* key : {"clr_drop_probability",
                                "stable_drop_probability"}) {
            if (!tolerances.contains(key)) {
                throw std::runtime_error(
                    std::string("clr_tolerances requires ") + key);
            }
        }
        experiment_config.clr_drop_threshold = parse_probability_threshold(
            tolerances.at("clr_drop_probability"),
            "clr_tolerances.clr_drop_probability");
        experiment_config.stable_drop_threshold = parse_probability_threshold(
            tolerances.at("stable_drop_probability"),
            "clr_tolerances.stable_drop_probability");
        if (experiment_config.clr_drop_threshold >
            experiment_config.stable_drop_threshold) {
            throw std::runtime_error(
                "clr_tolerances.clr_drop_probability must not exceed stable_drop_probability");
        }
        experiment_config.clr_tolerances_configured = true;
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

    experiment_telemetry.initialize(output_dir);
}

inline void finalize_experiment_telemetry() {
    experiment_telemetry.flush();
}

}  // namespace AstraSimNs3

#endif /* __ASTRA_SIM_NS3_EXPERIMENT_CONFIG_HH__ */
