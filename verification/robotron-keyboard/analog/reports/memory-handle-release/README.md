# Static memory public handle release

Three native processes compare original, disabled and enabled behavior on the selected continuous-memory runtime. Two rounds release the static memory and both materialized word handles through each public VPI API (12 calls per process). Every call returns success and preserves identity, scope, size, values and, when enabled, exact metadata plus dense array inventory. HDL writes between rounds and final continuation agree.

These APIs do not destroy these handles. This evidence does not qualify native memory deletion, scope teardown, allocator address reuse, dynamic arrays, subclasses or continuous board execution. The runtime build and all native outputs are retained. Three replay/rejection tests cover missing release events and changed inventory.
