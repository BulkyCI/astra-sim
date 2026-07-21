/******************************************************************************
This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*******************************************************************************/

#ifndef ASTRA_SIM_SYSTEM_COMMON_HH_
#define ASTRA_SIM_SYSTEM_COMMON_HH_

#include <cstdint>
#include <string>

namespace AstraSim {

typedef unsigned long long Tick;

constexpr uint64_t CLOCK_PERIOD = 1;           // 1ns
constexpr uint64_t FREQ = 1000 * 1000 * 1000;  // 1GHz

enum time_type_e { SE = 0, MS, US, NS, FS };

enum req_type_e { UINT8 = 0, BFLOAT16, FP32 };

enum class ComType {
    None = 0,
    Reduce_Scatter,
    All_Gather,
    All_Reduce,
    All_to_All,
    All_Reduce_All_to_All
};

// Communication domains are trace semantics. They must never be inferred
// from a topology dimension, queue id, or ns-3 priority group.
enum class ParallelismDomain : uint8_t {
    Unknown = 0,
    Tensor,
    Pipeline,
    Data,
};

enum class TransportRole : uint8_t {
    Unknown = 0,
    CollectivePayload,
    PointToPointPayload,
    RendezvousControl,
    ProvenanceControl,
    BackgroundTraffic,
};

struct OperationContext {
    ParallelismDomain parallelism_domain = ParallelismDomain::Unknown;
    TransportRole transport_role = TransportRole::Unknown;
    ComType collective_type = ComType::None;
    uint32_t training_step = 0;
    uint64_t workload_node_id = 0;
    uint64_t message_sequence = 0;
};

inline bool is_dp_all_reduce_payload(const OperationContext& context) {
    return context.parallelism_domain == ParallelismDomain::Data &&
           context.transport_role == TransportRole::CollectivePayload &&
           context.collective_type == ComType::All_Reduce;
}

struct timespec_t {
    time_type_e time_res;
    long double time_val;
};

struct sim_request {
    uint32_t srcRank = 0;
    uint32_t dstRank = 0;
    uint32_t tag = 0;
    req_type_e reqType = UINT8;
    uint64_t reqCount = 0;
    uint32_t vnet = 0;
    uint32_t layerNum = 0;
    OperationContext operation;
};

class MetaData {
  public:
    timespec_t timestamp;
};

enum class CollectiveOptimization { Baseline = 0, LocalBWAware };

enum class CollectiveBarrier { Blocking = 0, Non_Blocking };

enum class SchedulingPolicy { LIFO = 0, FIFO, EXPLICIT, None };

enum class IntraDimensionScheduling {
    FIFO = 0,
    RG,
    SmallestFirst,
    LessRemainingPhaseFirst
};

enum class InterDimensionScheduling {
    Ascending = 0,
    OnlineGreedy,
    RoundRobin,
    OfflineGreedy,
    OfflineGreedyFlex
};

enum class InjectionPolicy {
    Infinite = 0,
    Aggressive,
    SemiAggressive,
    ExtraAggressive,
    Normal
};

enum class PacketRouting { Hardware = 0, Software };

enum class BusType { Both = 0, Shared, Mem };

enum class StreamState {
    Created = 0,
    Transferring,
    Ready,
    Executing,
    Zombie,
    Dead
};

enum class EventType {
    CallEvents = 0,
    General,
    RendezvousSend,
    RendezvousRecv,
    PacketReceived,
    PacketSent,
    Rec_Finished,
    Send_Finished,
    Processing_Finished,
    NPU_to_MA,
    MA_to_NPU,
    Consider_Process,
    Consider_Retire,
    Consider_Send_Back,
    StreamInit,
    CommProcessingFinished,
    CollectiveCommunicationFinished,
    CompFinished,
    MemLoadFinished,
    MemStoreFinished
};

}  // namespace AstraSim

#endif  // ASTRA_SIM_SYSTEM_COMMON_HH_
