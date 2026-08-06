/******************************************************************************
This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*******************************************************************************/

#include "astra-sim/system/CommunicatorGroup.hh"

#include <algorithm>
#include <stdexcept>

#include "astra-sim/system/CollectivePlan.hh"
#include "astra-sim/system/Sys.hh"

using namespace AstraSim;

CommunicatorGroup::CommunicatorGroup(int comm_group_id,
                                     std::vector<int> involved_NPUs,
                                     Sys* generator) {
    set_id(comm_group_id);
    this->involved_NPUs = involved_NPUs;
    this->generator = generator;
    std::sort(this->involved_NPUs.begin(), this->involved_NPUs.end());
    if (std::adjacent_find(this->involved_NPUs.begin(),
                           this->involved_NPUs.end()) !=
        this->involved_NPUs.end()) {
        throw std::invalid_argument(
            "Communicator group membership must not contain duplicate ranks");
    }

    // -1 means the rank is not in the comm group.
    int position = -1;
    for (size_t i = 0; i < this->involved_NPUs.size(); ++i) {
        if (this->involved_NPUs[i] == generator->id) {
            position = static_cast<int>(i);
            break;
        }
    }
    pos_in_group = position;
}

CommunicatorGroup::~CommunicatorGroup() {
    for (auto cg : comm_plans) {
        CollectivePlan* cp = cg.second;
        delete cp;
    }
}

void CommunicatorGroup::set_id(int id) {
    // id 0 is reserved for the default comm group, which is all ranks.
    // CTRL+F "default communication group"
    assert(id > 0);
    this->id = id;
    this->num_streams = id * 1000000;
}

CollectivePlan* CommunicatorGroup::get_collective_plan(ComType comm_type, uint64_t workload_node_id) {
    if (comm_plans.find(comm_type) != comm_plans.end()) {
        return comm_plans[comm_type];
    }

    // A per-group algorithm override always runs over the group's own single
    // logical dimension, whether or not the group spans the cluster. The plan
    // owns the freshly minted implementation and the topology.
    CollectiveImpl* group_impl =
        generator->collective_impl_lookup->make_group_collective_impl(comm_type,
                                                                      id);
    if (group_impl != nullptr) {
        LogicalTopology* logical_topology = new RingTopology(
            RingTopology::Dimension::Local, generator->id, involved_NPUs);
        comm_plans[comm_type] = new CollectivePlan(
            logical_topology, std::vector<CollectiveImpl*>{group_impl},
            std::vector<bool>(1, true), true);
        return comm_plans[comm_type];
    }

    if (static_cast<uint64_t>(generator->total_nodes) == involved_NPUs.size()) {
        LogicalTopology* logical_topology =
            generator->get_logical_topology(comm_type);
        std::vector<CollectiveImpl*> collective_implementation =
            generator->collective_impl_lookup->get_collective_impl(comm_type, workload_node_id);
        std::vector<bool> dimensions_involved(10, true);
        bool should_be_removed = false;
        comm_plans[comm_type] =
            new CollectivePlan(logical_topology, collective_implementation,
                               dimensions_involved, should_be_removed);
        return comm_plans[comm_type];
    } else {
        std::vector<CollectiveImpl*> collective_implementation =
            generator->collective_impl_lookup->get_collective_impl(comm_type, workload_node_id);
        if (collective_implementation.size() > 1) {
            // This means that everything fell through and we got a native collective that is multi-dimensional.
            // (Custom collective always assumes 1 dimension).
            // The current logic requires that, for a comm group that is smaller than the whole cluster,
            // we reduce everything to one dimension since the logical dimension no longer matches/matters.
            // TODO: Revisit whether the choice to override with Ring (instead of e.g. first dimension in list)
            // was a good choice.
            collective_implementation = std::vector<CollectiveImpl*>{
                new CollectiveImpl(CollectiveImplType::Ring)};
        }
        LogicalTopology* logical_topology = new RingTopology(
            RingTopology::Dimension::Local, generator->id, involved_NPUs);
        std::vector<bool> dimensions_involved(1, true);
        bool should_be_removed = true;
        comm_plans[comm_type] =
            new CollectivePlan(logical_topology, collective_implementation,
                               dimensions_involved, should_be_removed);
        return comm_plans[comm_type];
    }
    assert(false);
    return nullptr;
}

int CommunicatorGroup::get_position_in_group() {
    if (pos_in_group < 0) {
        throw std::runtime_error(
            "Local rank is not a member of the referenced communicator group");
    }
    return pos_in_group;
}
