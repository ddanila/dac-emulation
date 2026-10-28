# Native destructor trace and stale registry diagnostic

Environment-gated trace statements are the only changes from the preceding ASAN candidate. Six native parameter destructor entries bind to the exact final observed pointers and binary/real/string families; the parameter registry drains from six to zero. Two native memory destructor entries bind to the final observed array addresses and the memory registry drains from two to zero. Native roots drain from two to zero before VPI unload. All seven post-cleanup inventories safely refuse with zero output. Original, disabled and enabled HDL output matches exactly, all exits are clean and five replay/rejection tests pass.

The diagnostic finds stale registrations after root deletion: four initialized scopes, four scope metadata records, 33 attached objects, 33 object IDs, 33 object types, four ports, four port slots and 18 port bits remain. allTrackedRegistriesEmpty is false. This is a retained teardown gap, not acceptance of complete cleanup. The candidate changes no registration lifecycle; it only reports counts and destructor entries.

ASAN fixture loader-table exclusion, disabled leak detection and disabled Valgrind annotations remain as documented in the preceding reports. This trace does not prove every runtime destructor, custom-pool safety, dangling-handle safety or board teardown.
