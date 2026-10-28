/*
 * Copyright (c) 2001-2026 Stephen Williams (steve@icarus.com)
 *
 *    This source code is free software; you can redistribute it
 *    and/or modify it in source code form under the terms of the GNU
 *    General Public License as published by the Free Software
 *    Foundation; either version 2 of the License, or (at your option)
 *    any later version.
 *
 *    This program is distributed in the hope that it will be useful,
 *    but WITHOUT ANY WARRANTY; without even the implied warranty of
 *    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *    GNU General Public License for more details.
 *
 *    You should have received a copy of the GNU General Public License
 *    along with this program; if not, write to the Free Software
 *    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
 */

# include  "compile.h"
# include  "vpi_priv.h"
# include  "symbols.h"
# include  "statistics.h"
# include  "config.h"
#ifdef CHECK_WITH_VALGRIND
# include  "vvp_cleanup.h"
#endif
# include  <vector>
# include  <cstring>
# include  <cstdlib>
# include  <cassert>
# include  "ivl_alloc.h"

using namespace std;

static vector<vpiHandle> vpip_root_table;

// Native compilation handoffs register initialized ownership. These sets are
// not populated by observer-supplied or arbitrary VPI object pointers.
static set<vpiHandle> robotron_initialized_scopes;
static set<vpiHandle> robotron_attached_objects;
struct robotron_scope_metadata_registration {
    unsigned long long id;
    const char *name, *definition;
    size_t name_bytes, definition_bytes;
};
static map<__vpiScope*,robotron_scope_metadata_registration> robotron_scope_metadata;
static map<vpiHandle,unsigned long long> robotron_object_ids;
static unsigned long long robotron_next_object_id=0;
static map<vpiHandle,int> robotron_object_types;
struct robotron_port_registration {const char*name;size_t bytes;bool ready;};
static map<vpiPortInfo*,robotron_port_registration> robotron_ports;
static map<vvp_net_t**,vpiPortInfo*> robotron_port_slots;
static set<vpiPortBitInfo*> robotron_port_bits;
extern "C" void robotron_vvp_port_reference_resolved(vvp_net_t**slot)
{
    auto found=robotron_port_slots.find(slot);
    if(found!=robotron_port_slots.end())robotron_ports.at(found->second).ready=true;
}

static vpiHandle make_subset_iterator_(int type_code, const vector<vpiHandle>&table);

vpiHandle vpip_make_root_iterator(int type_code)
{
      return make_subset_iterator_(type_code, vpip_root_table);
}

void vpip_make_root_iterator(__vpiHandle**&table, unsigned&ntable)
{
      table = &vpip_root_table[0];
      ntable = vpip_root_table.size();
}

#ifdef CHECK_WITH_VALGRIND
void port_delete(__vpiHandle*handle);
void port_bit_delete(__vpiHandle*handle);

/* Class definitions need to be cleaned up at the end. */
static class_type **class_list = 0;
static unsigned class_list_count = 0;

static void delete_sub_scopes(__vpiScope *scope)
{
      for (unsigned idx = 0; idx < scope->intern.size(); idx += 1) {
	    vpiHandle item = (scope->intern)[idx];
	    __vpiScope*lscope = static_cast<__vpiScope*>(item);
	    switch(item->get_type_code()) {
		case vpiFunction:
		case vpiTask:
		  contexts_delete(lscope);
		  // fallthrough
		case vpiModule:
		case vpiGenScope:
		case vpiNamedBegin:
		case vpiNamedFork:
		case vpiClassTypespec:
		  delete_sub_scopes(lscope);
		  vthreads_delete(lscope);
		  delete item;
		  break;
		case vpiMemory:
		case vpiNetArray:
		  memory_delete(item);
		  break;
		case vpiModPath:
		    /* The destination ModPath is cleaned up later. */
		  delete item;
		  break;
		case vpiInterModPath:
		  delete item;
		  break;
		case vpiNamedEvent:
		  named_event_delete(item);
		  break;
		case vpiNet:
		case vpiReg:
		case vpiIntegerVar:
		case vpiLongIntVar:
		case vpiShortIntVar:
		case vpiIntVar:
		case vpiByteVar:
		case vpiBitVar:
		  signal_delete(item);
		  break;
		case vpiParameter:
		  parameter_delete(item);
		  break;
		case vpiRealVar:
		  real_delete(item);
		  break;
		case vpiEnumTypespec:
		  enum_delete(item);
		  break;
		case vpiPort:
		  port_delete(item);
		  break;
		case vpiPortBit:
		  port_bit_delete(item);
		  break;
		case vpiStringVar:
		  string_delete(item);
		  break;
		case vpiClassVar:
		  class_delete(item);
		  break;
		case vpiArrayVar:
		  array_delete(item);
		  break;
		default:
		  fprintf(stderr, "Need support for type: %d\n",
		          item->get_type_code());
		  assert(0);
		  break;
	    }
      }
      scope->intern.clear();

	/* Save any class definitions to clean up later. */
      map<std::string, class_type*>::iterator citer;
      for (citer = scope->classes.begin();
           citer != scope->classes.end(); ++ citer ) {
	    class_list_count += 1;
	    class_list = static_cast<class_type **>
	                 (realloc(class_list,
	                  class_list_count*sizeof(class_type **)));
	    class_list[class_list_count-1] = citer->second;
      }
}

void root_table_delete(void)
{
      if(getenv("ROBOTRON_TEARDOWN_TRACE")) fprintf(stdout,"TEARDOWN_REGISTRIES %s %zu %zu %zu %zu %zu %zu %zu %zu %zu\n","before",vpip_root_table.size(),robotron_initialized_scopes.size(),robotron_scope_metadata.size(),robotron_attached_objects.size(),robotron_object_ids.size(),robotron_object_types.size(),robotron_ports.size(),robotron_port_slots.size(),robotron_port_bits.size());
      for (unsigned idx = 0; idx < vpip_root_table.size(); idx += 1) {
	    __vpiScope *scope = static_cast<__vpiScope *>
	          (vpip_root_table[idx]);
	    vthreads_delete(scope);
	    delete_sub_scopes(scope);
	    delete scope;
      }
      vpip_root_table.clear();
      if(getenv("ROBOTRON_TEARDOWN_TRACE")) fprintf(stdout,"TEARDOWN_REGISTRIES %s %zu %zu %zu %zu %zu %zu %zu %zu %zu\n","after",vpip_root_table.size(),robotron_initialized_scopes.size(),robotron_scope_metadata.size(),robotron_attached_objects.size(),robotron_object_ids.size(),robotron_object_types.size(),robotron_ports.size(),robotron_port_slots.size(),robotron_port_bits.size());

	/* Clean up all the class definitions. */
      for (unsigned idx = 0; idx < class_list_count; idx += 1) {
            class_def_delete(class_list[idx]);
      }
      free(class_list);
      class_list = 0;
      class_list_count = 0;
}
#endif

static void construct_scope_fullname(__vpiScope*ref, char*buf)
{
      if (ref->scope) {
	    construct_scope_fullname(ref->scope, buf);
	      // Add a "." separator, unless this is for a package
	    if (ref->scope->get_type_code() != vpiPackage) {
		  strcat(buf, ".");
	    }
      }

      strcat(buf, ref->scope_name());
	// For a package, add a "::" to the end
      if (ref->get_type_code() == vpiPackage) strcat(buf, "::");
}

static const char* scope_get_type(int code)
{
      switch (code) {
          case vpiModule:
            return "vpiModule";
          case vpiGenScope:
            return "vpiGenScope";
          case vpiFunction:
            return "vpiFunction";
          case vpiTask:
            return "vpiTask";
          case vpiNamedBegin:
            return "vpiNamedBegin";
          case vpiNamedFork:
            return "vpiNamedFork";
          default:
            fprintf(stderr, "VPI error: invalid scope type code %d.\n", code);
            return NULL;
      }
}

static char* scope_get_str(int code, vpiHandle obj)
{
      __vpiScope*ref = dynamic_cast<__vpiScope*>(obj);
      assert(ref);

      char buf[4096];  // XXX is a fixed buffer size really reliable?
      const char *p=0;
      switch (code) {
	  case vpiDefFile:
	    p = file_names[ref->def_file_idx];
	    break;

	  case vpiFile:
	    p = file_names[ref->file_idx];
	    break;

	  case vpiFullName:
	    buf[0] = 0;
	    construct_scope_fullname(ref, buf);
	    p = buf;
	    break;

	  case vpiName:
	    p = ref->scope_name();
	    break;

	  case vpiDefName:
	    p = ref->scope_def_name();
	    break;

	  case vpiType:
	    p = scope_get_type(code);
	    break;

	  default:
	    fprintf(stderr, "VPI error: invalid scope string code %d.\n", code);
	    return NULL;
      }
      return simple_set_rbuf_str(p);
}

static vpiHandle scope_get_handle(int code, vpiHandle obj)
{
      __vpiScope*rfp = dynamic_cast<__vpiScope*>(obj);
      assert(rfp);

      switch (code) {

	  case vpiScope:
	    return rfp->scope;

	  case vpiModule:
	    return rfp->scope;
      }

      return 0;
}

/* compares vpiType's considering object classes */
static int compare_types(int code, int type)
{
	/* NOTE: The Verilog VPI does not for any object support
	   vpiScope as an iterator parameter, so it is used here as a
	   means to scan everything in the *current* scope. */
      if (code == vpiScope)
	    return 1;

      if (code == type)
	    return 1;

      if ( code == vpiInternalScope &&
	     (type == vpiModule ||
	     type == vpiGenScope ||
	     type == vpiFunction ||
	     type == vpiTask ||
	     type == vpiNamedBegin ||
	     type == vpiNamedFork) )
	    return 1;

      if ( code == vpiInstance &&
	    (type == vpiModule ||
	     type == vpiProgram ||
	     type == vpiInterface ||
	     type == vpiPackage) )
	    return 1;

      if ( code == vpiVariables &&
	     (type == vpiIntegerVar  ||
	      type == vpiBitVar      ||
	      type == vpiByteVar     ||
	      type == vpiShortIntVar ||
	      type == vpiIntVar      ||
	      type == vpiLongIntVar  ||
	      type == vpiTimeVar     ||
	      type == vpiRealVar))
	    return 1;

      return 0;
}

static vpiHandle make_subset_iterator_(int type_code, const vector<vpiHandle>&table)
{
      unsigned mcnt = 0, ncnt = 0;
      vpiHandle*args;

      for (unsigned idx = 0; idx < table.size(); idx += 1)
	    if (compare_types(type_code, table[idx]->get_type_code()))
		  mcnt += 1;

      if (mcnt == 0)
	    return 0;

      args = static_cast<vpiHandle*>(calloc(mcnt, sizeof(vpiHandle)));
      for (unsigned idx = 0; idx < table.size(); idx += 1)
	    if (compare_types(type_code, table[idx]->get_type_code()))
		  args[ncnt++] = table[idx];

      assert(ncnt == mcnt);

      return vpip_make_iterator(mcnt, args, true);
}

/*
 * This function implements the vpi_iterate method for vpiModule and
 * similar objects. The vpi_iterate allows the user to iterate over
 * things that are contained in the scope object, by generating an
 * iterator for the requested set of items.
 */
static vpiHandle module_iter(int code, vpiHandle obj)
{
      __vpiScope*ref = dynamic_cast<__vpiScope*>(obj);
      assert(ref);

      return make_subset_iterator_(code, ref->intern);
}


__vpiScope::__vpiScope(const char*nam, const char*tnam, bool auto_flag)
: is_automatic_(auto_flag)
{
      name_ = vpip_name_string(nam);
      tname_ = vpip_name_string(tnam? tnam : "");
}

int __vpiScope::vpi_get(int code)
{
      switch (code) {
	  case vpiCellInstance:
	    return is_cell? 1 : 0;

	  case vpiDefLineNo:
	    return def_lineno;

	  case vpiLineNo:
	    return lineno;

	  case vpiTimeUnit:
	    return time_units;

	  case vpiTimePrecision:
	    return time_precision;

	  case vpiTopModule:
	    return 0x0 == scope;

          case vpiAutomatic:
	    return is_automatic_? 1 : 0;
      }

      return vpiUndefined;
}


char*__vpiScope::vpi_get_str(int code)
{ return scope_get_str(code, this); }

vpiHandle __vpiScope::vpi_handle(int code)
{ return scope_get_handle(code, this); }

vpiHandle __vpiScope::vpi_iterate(int code)
{ return module_iter(code, this); }


class vpiScopeModule  : public __vpiScope {
    public:
      inline vpiScopeModule(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam,false) { }
      int get_type_code(void) const override { return vpiModule; }
};

struct vpiScopePackage  : public __vpiScope {
      inline vpiScopePackage(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam) { }
      int get_type_code(void) const override { return vpiPackage; }
};

struct vpiScopeTask  : public __vpiScope {
      inline vpiScopeTask(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam) { }
      int get_type_code(void) const override { return vpiTask; }
};

struct vpiScopeTaskAuto  : public __vpiScope {
      inline vpiScopeTaskAuto(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam,true) {  }
      int get_type_code(void) const override { return vpiTask; }
};

struct vpiScopeBegin  : public __vpiScope {
      inline vpiScopeBegin(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam,false) { }
      int get_type_code(void) const override { return vpiNamedBegin; }
};

class vpiScopeBeginAuto  : public __vpiScope {
    public:
      inline vpiScopeBeginAuto(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam,true) {  }
      int get_type_code(void) const override { return vpiNamedBegin; }
};

struct vpiScopeGenerate  : public __vpiScope {
      inline vpiScopeGenerate(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam) { }
      int get_type_code(void) const override { return vpiGenScope; }
};

struct vpiScopeFork  : public __vpiScope {
      inline vpiScopeFork(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam,false) { }
      int get_type_code(void) const override { return vpiNamedFork; }
};

class vpiScopeForkAuto  : public __vpiScope {
    public:
      inline vpiScopeForkAuto(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam,true) {  }
      int get_type_code(void) const override { return vpiNamedFork; }
};

struct vpiScopeClass  : public __vpiScope {
      inline vpiScopeClass(const char*nam, const char*tnam)
      : __vpiScope(nam,tnam) { }
      int get_type_code(void) const override { return vpiClassTypespec; }
};

/*
 * The current_scope is a compile time concept. As the vvp source is
 * compiled, items that have scope are placed in the current
 * scope. The ".scope" directives select the scope that is current.
 */
static __vpiScope*current_scope = 0;

void vpip_attach_to_scope(__vpiScope*scope, vpiHandle obj)
{
      assert(scope);
      scope->intern.push_back(obj);
      robotron_attached_objects.insert(obj);
      if(!robotron_object_ids.count(obj)) {
          if(robotron_next_object_id==~0ULL)abort();
          robotron_object_ids[obj]=++robotron_next_object_id;
          robotron_object_types[obj]=obj->get_type_code();
      }
}

/*
 * When the compiler encounters a scope declaration, this function
 * creates and initializes a __vpiScope object with the requested name
 * and within the addressed parent. The label is used as a key in the
 * symbol table and the name is used to construct the actual object.
 */
void
compile_scope_decl(char*label, char*type, char*name, char*tname,
                   char*parent, long file_idx, long lineno,
                   long def_file_idx, long def_lineno, long is_cell)
{
      count_vpi_scopes += 1;
      char vec_type;
      char sign_flag;
      unsigned wid;

      __vpiScope*scope;
      if (strcmp(type,"module") == 0) {
	    scope = new vpiScopeModule(name, tname);
      } else if ( sscanf(type, "function.vec%c.%c%u", &vec_type, &sign_flag, &wid) == 3 ) {
	    int type_code;
	    if (sign_flag=='s') {
		  type_code = vpiSizedSignedFunc;
	    } else if (sign_flag=='u') {
		  type_code = vpiSizedFunc;
	    } else if (sign_flag=='i') {
		  type_code = vpiIntFunc;
	    } else {
		  assert(0);
		  type_code = vpiSizedFunc;
	    }
	    vvp_bit4_t init_val = vec_type == '4' ? BIT4_X : BIT4_0;
	    scope = new vpiScopeFunction(name, tname, false, type_code, wid, init_val);

      } else if ( sscanf(type, "autofunction.vec%c.%c%u", &vec_type, &sign_flag, &wid) == 3 ) {
	    int type_code;
	    switch (sign_flag) {
		case 's':
		  type_code = vpiSizedSignedFunc;
		  break;
		case 'u':
		  type_code = vpiSizedFunc;
		  break;
		default:
		  assert(0);
		  type_code = vpiSizedFunc;
		  break;
	    }
	    vvp_bit4_t init_val = vec_type == '4' ? BIT4_X : BIT4_0;
	    scope = new vpiScopeFunction(name, tname, true, type_code, wid, init_val);

      } else if (strcmp(type,"function.obj") == 0) {
	    scope = new vpiScopeFunction(name, tname, false, vpiSizedFunc, 0, BIT4_0);
      } else if (strcmp(type,"autofunction.obj") == 0) {
	    scope = new vpiScopeFunction(name, tname, true, vpiSizedFunc, 0, BIT4_0);
      } else if (strcmp(type,"function.real") == 0) {
	    scope = new vpiScopeFunction(name, tname, false, vpiRealFunc, 0, BIT4_0);
      } else if (strcmp(type,"autofunction.real") == 0) {
	    scope = new vpiScopeFunction(name, tname, true, vpiRealFunc, 0, BIT4_0);
      } else if (strcmp(type,"function.str") == 0) {
	    scope = new vpiScopeFunction(name, tname, false, vpiOtherFunc, 0, BIT4_0);
      } else if (strcmp(type,"autofunction.str") == 0) {
	    scope = new vpiScopeFunction(name, tname, true, vpiOtherFunc, 0, BIT4_0);
      } else if (strcmp(type,"function.void") == 0) {
	    scope = new vpiScopeFunction(name, tname, false, vpiOtherFunc, 0, BIT4_0);
      } else if (strcmp(type,"autofunction.void") == 0) {
	    scope = new vpiScopeFunction(name, tname, true, vpiOtherFunc, 0, BIT4_0);
      } else if (strcmp(type,"task") == 0) {
	    scope = new vpiScopeTask(name, tname);
      } else if (strcmp(type,"autotask") == 0) {
	    scope = new vpiScopeTaskAuto(name, tname);
      } else if (strcmp(type,"fork") == 0) {
	    scope = new vpiScopeFork(name, tname);
      } else if (strcmp(type,"autofork") == 0) {
	    scope = new vpiScopeForkAuto(name, tname);
      } else if (strcmp(type,"begin") == 0) {
	    scope = new vpiScopeBegin(name, tname);
      } else if (strcmp(type,"autobegin") == 0) {
	    scope = new vpiScopeBeginAuto(name, tname);
      } else if (strcmp(type,"generate") == 0) {
	    scope = new vpiScopeGenerate(name, tname);
      } else if (strcmp(type,"package") == 0) {
	    scope = new vpiScopePackage(name, tname);
      } else if (strcmp(type,"class") == 0) {
	    scope = new vpiScopeClass(name, tname);
      } else {
	    scope = new vpiScopeModule(name, tname);
	    assert(0);
      }

      scope->file_idx = (unsigned) file_idx;
      scope->lineno  = (unsigned) lineno;
      scope->def_file_idx = (unsigned) def_file_idx;
      scope->def_lineno  = (unsigned) def_lineno;
      scope->item = 0;
      scope->nitem = 0;
      scope->live_contexts = 0;
      scope->free_contexts = 0;

      if (is_cell) scope->is_cell = true;
      else scope->is_cell = false;

      current_scope = scope;

      compile_vpi_symbol(label, scope);

      free(label);
      free(type);
      delete[] name;
      delete[] tname;

      if (parent) {
	    static vpiHandle obj;
	    compile_vpi_lookup(&obj, parent);
	    assert(obj);
	    __vpiScope*sp = dynamic_cast<__vpiScope*>(obj);
	    vpip_attach_to_scope(sp, scope);
	    scope->scope = dynamic_cast<__vpiScope*>(obj);

	      /* Inherit time units and precision from the parent scope. */
	    scope->time_units = sp->time_units;
	    scope->time_precision = sp->time_precision;

      } else {
	    scope->scope = 0x0;

	    vpip_root_table.push_back(scope);

	      /* Root scopes inherit time_units and precision from the
	         system precision. */
	    scope->time_units = vpip_get_time_precision();
	    scope->time_precision = vpip_get_time_precision();
      }
      robotron_initialized_scopes.insert(scope);
      robotron_scope_metadata[scope]={robotron_scope_metadata.size()+1,
          scope->scope_name(),scope->scope_def_name(),
          strlen(scope->scope_name())+1,strlen(scope->scope_def_name())+1};
}

void compile_scope_recall(char*symbol)
{
	/* A __vpiScope starts with a __vpiHandle structure so this is
	   a safe cast. We need the (void*) to avoid a dereferenced
	   type punned pointer warning from some gcc compilers. */
      compile_vpi_lookup((vpiHandle*)(void*)&current_scope, symbol);
      assert(current_scope);
}

/*
 * This function handles the ".timescale" directive in the vvp
 * source. It sets in the current scope the specified units value.
 */
void compile_timescale(long units, long precision)
{
      assert(current_scope);
      current_scope->time_units = units;
      current_scope->time_precision = precision;
}

__vpiScope* vpip_peek_current_scope(void)
{
      return current_scope;
}

void vpip_attach_to_current_scope(vpiHandle obj)
{
      vpip_attach_to_scope(current_scope, obj);
}

__vpiScope* vpip_peek_context_scope(void)
{
      __vpiScope*scope = current_scope;

        /* A context is allocated for each automatic task or function.
           Storage for nested scopes (named blocks) is allocated in
           the parent context. */
      while (scope->scope && scope->scope->is_automatic())
            scope = scope->scope;

      return scope;
}

unsigned vpip_add_item_to_context(automatic_hooks_s*item,
                                  __vpiScope*scope)
{
      assert(scope);
      assert(scope->is_automatic());

      unsigned idx = scope->nitem++;

      if (scope->item == 0)
	    scope->item = static_cast<automatic_hooks_s**>
	                  (malloc(sizeof(automatic_hooks_s*)));
      else
	    scope->item = static_cast<automatic_hooks_s**>
	                  (realloc(scope->item,
	                   sizeof(automatic_hooks_s*)*scope->nitem));

      scope->item[idx] = item;

        /* Offset the context index by 2 to leave space for the list links. */
      return 2 + idx;
}


vpiPortInfo::vpiPortInfo( __vpiScope *parent,
              unsigned index,
              int vpi_direction,
              unsigned width,
              const char *name,
              char* buffer) :
      parent_(parent),
      index_(index),
      direction_(vpi_direction),
      width_(width),
      name_(name)
{
      robotron_ports[this]={name,name?strlen(name)+1:0,buffer==nullptr};
      robotron_port_slots[&ref_]=this;
      if (buffer != nullptr) functor_ref_lookup(&ref_, buffer);
      else ref_ = nullptr;
}

vpiPortInfo::~vpiPortInfo()
{
      delete[] name_;
}

#ifdef CHECK_WITH_VALGRIND
void port_delete(__vpiHandle *handle)
{
      delete dynamic_cast<vpiPortInfo *>(handle);
}
#endif

int vpiPortInfo::vpi_get(int code)
{
      switch( code ) {

        case vpiDirection :
          return direction_;
        case vpiPortIndex :
          return index_;
        case vpiSize :
          return width_;
        default :
          return vpiUndefined;
      }

}


char *vpiPortInfo::vpi_get_str(int code)
{
      switch( code ) {
        case vpiName :
          return simple_set_rbuf_str(name_);
        default :
          return NULL;
      }

}


vpiHandle vpiPortInfo::vpi_handle(int code)
{

      switch (code) {

          case vpiParent:
          case vpiScope:
          case vpiModule:
            return parent_;
          default :
            break;
      }

      return 0;
}

static vpiHandle portinfo_iterate(int code, vpiHandle ref)
{
      vpiPortInfo*rfp = dynamic_cast<vpiPortInfo*>(ref);
      assert(rfp);
      unsigned width = rfp->get_width();

      switch (code) {
	  case vpiBit: {
	    vpiHandle*args = static_cast<vpiHandle*>(calloc(width, sizeof(vpiHandle*)));

	    for (unsigned i = 0; i<rfp->port_bits_.size(); i++) {
		  args[i] = rfp->port_bits_[i];
	    }

	    return vpip_make_iterator(width, args, true);
	  }
      }
      return 0;
}

vpiHandle vpiPortInfo::vpi_iterate(int code)
{
      return portinfo_iterate(code, this);
}


vpiPortBitInfo::vpiPortBitInfo(vpiPortInfo *parent,
                               unsigned bit) :
      parent_(parent),
      bit_(bit)
{
      robotron_port_bits.insert(this);
}

vpiPortBitInfo::~vpiPortBitInfo()
{
}

#ifdef CHECK_WITH_VALGRIND
void port_bit_delete(__vpiHandle *handle)
{
      delete dynamic_cast<vpiPortBitInfo *>(handle);
}
#endif

vpiHandle vpiPortBitInfo::vpi_handle(int code)
{

      switch (code) {
          case vpiParent:
            return parent_;
          default :
            break;
      }

      return 0;
}

int vpiPortBitInfo::vpi_get(int code)
{
      switch( code ) {
        case vpiBit :
          return bit_;
        default :
          break;
      }

      return 0;
}

/* Port info is meta-data to allow vpi queries of the port signature of modules for
 * code-generators etc.  There are no actual nets corresponding to instances of module ports
 * as elaboration directly connects nets connected through module ports.
 */
void compile_port_info( unsigned index, int vpi_direction, unsigned width, const char *name, char* buffer )
{
      vpiPortInfo* obj = new vpiPortInfo( vpip_peek_current_scope(),
                                          index, vpi_direction, width, name, buffer );
      vpip_attach_to_current_scope(obj);

	// Create vpiPortBit objects
      for (unsigned i=0; i<width; i++) {
	    vpiPortBitInfo* obj_bit = new vpiPortBitInfo(obj, i);
	    obj->add_port_bit(obj_bit);
	    vpip_attach_to_current_scope(obj_bit);
      }
}

// Scope membership is independent of registered live-thread lifetime.
#include "schedule.h"
extern "C" unsigned long long robotron_vvp_thread_identity(vthread_t);
static int robotron_static_scopes(vector<__vpiScope*>& scopes)
{
    set<__vpiScope*> seen;
    for(auto root:vpip_root_table){
        if(!robotron_initialized_scopes.count(root))return -1;
        auto scope=dynamic_cast<__vpiScope*>(root);
        if(!scope || scope->scope)return -1;
        scopes.push_back(scope);
    }
    for(size_t i=0;i<scopes.size();++i){
        auto scope=scopes[i];
        if(!seen.insert(scope).second || scope->is_automatic() || scope->nitem ||
           scope->item || scope->live_contexts || scope->free_contexts)return -1;
        for(auto item:scope->intern){
            if(!robotron_attached_objects.count(item))return -1;
            auto child=dynamic_cast<__vpiScope*>(item);
            if(!child)continue;
            if(!robotron_initialized_scopes.count(child) || child->scope!=scope)return -1;
            scopes.push_back(child);
        }
    }
    return scopes.empty() || scopes.size()!=robotron_initialized_scopes.size()?-1:0;
}
extern "C" int robotron_vvp_scope_inventory(FILE* out)
{
    vector<__vpiScope*> scopes;
    if(!out || robotron_static_scopes(scopes))return -1;
    map<__vpiScope*,unsigned long long> ids;
    for(size_t i=0;i<scopes.size();++i)ids[scopes[i]]=i+1;
    if(fprintf(out,"VSC_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
    for(auto scope:scopes){
        map<unsigned long long,vthread_t> members;
        for(auto thread:scope->threads){
            auto id=robotron_vvp_thread_identity(thread);
            if(!id || !members.insert({id,thread}).second)return -1;
        }
        if(fprintf(out,"VSC_SCOPE %llu %p %llu %d %zu\n",ids[scope],(void*)scope,
                   scope->scope?ids.at(scope->scope):0,scope->get_type_code(),members.size())<0)return -1;
        for(auto member:members)if(fprintf(out,"VSC_MEMBER %llu\n",member.first)<0)return -1;
    }
    return fprintf(out,"VSC_END %zu\n",scopes.size())<0 || ferror(out)?-1:0;
}
extern "C" int robotron_vvp_scope_toggle(void)
{
    static __vpiScope* saved_scope=0;
    static vthread_t saved_thread=0;
    static unsigned long long saved_id=0;
    vector<__vpiScope*> scopes;
    if(robotron_static_scopes(scopes))return -1;
    if(saved_scope){
        bool found=false;for(auto scope:scopes)if(scope==saved_scope)found=true;
        if(!found || robotron_vvp_thread_identity(saved_thread)!=saved_id ||
           saved_scope->threads.count(saved_thread))return -1;
        saved_scope->threads.insert(saved_thread);
        saved_scope=0;saved_thread=0;saved_id=0;return 1;
    }
    for(auto scope:scopes){
        map<unsigned long long,vthread_t> members;
        for(auto thread:scope->threads){
            auto id=robotron_vvp_thread_identity(thread);
            if(!id)return -1;
            members[id]=thread;
        }
        if(members.empty())continue;
        saved_scope=scope;saved_id=members.begin()->first;saved_thread=members.begin()->second;
        scope->threads.erase(saved_thread);return 1;
    }
    return 0;
}

extern "C" unsigned long long robotron_vvp_scope_handle_id(const void*pointer)
{
    vector<__vpiScope*> scopes;if(robotron_static_scopes(scopes))return 0;
    for(size_t i=0;i<scopes.size();++i)if(scopes[i]==pointer)return i+1;
    return 0;
}

// Snapshot the complete admitted scope hierarchy once per metadata inventory.
extern "C" int robotron_vvp_scope_handle_ids(std::map<const void*,unsigned long long>*ids)
{
    if(!ids)return -1;
    vector<__vpiScope*> scopes;if(robotron_static_scopes(scopes))return -1;
    ids->clear();for(size_t i=0;i<scopes.size();++i)(*ids)[scopes[i]]=i+1;
    return 0;
}

// Static native lifetime only. Validate the complete graph before writing.
// Names are read only through their registered allocation and byte bounds.
#include <typeinfo>
static int robotron_scope_metadata_validate(vector<__vpiScope*>& scopes)
{
    if(robotron_static_scopes(scopes))return -1;
    for(auto scope:scopes) {
        auto found=robotron_scope_metadata.find(scope);
        if(found==robotron_scope_metadata.end() || !scope->classes.empty())return -1;
        const auto& r=found->second;
        if(scope->scope_name()!=r.name || scope->scope_def_name()!=r.definition)return -1;
        const auto& t=typeid(*scope);
        if(t!=typeid(vpiScopeModule) && t!=typeid(vpiScopePackage) &&
           t!=typeid(vpiScopeTask) && t!=typeid(vpiScopeBegin) &&
           t!=typeid(vpiScopeGenerate) && t!=typeid(vpiScopeFork) &&
           t!=typeid(vpiScopeFunction))return -1;
        if((scope->scoped_time.scope && scope->scoped_time.scope!=scope) ||
           (scope->scoped_stime.scope && scope->scoped_stime.scope!=scope) ||
           (scope->scoped_realtime.scope && scope->scoped_realtime.scope!=scope))return -1;
        for(auto item:scope->intern) {
            auto id=robotron_object_ids.find(item);
            auto type=robotron_object_types.find(item);
            if(id==robotron_object_ids.end() || type==robotron_object_types.end() ||
               item->get_type_code()!=type->second)return -1;
        }
    }
    return 0;
}
extern "C" int robotron_vvp_scope_metadata_inventory(FILE* out)
{
    vector<__vpiScope*> scopes;
    if(!out || robotron_scope_metadata_validate(scopes))return -1;
    if(fprintf(out,"VSM_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
    for(auto scope:scopes) {
        const auto& r=robotron_scope_metadata.at(scope);
        auto parent=scope->scope?robotron_scope_metadata.at(scope->scope).id:0;
        if(fprintf(out,"VSM_SCOPE %llu %llu %d %u %u %u %u %u %d %d\n",
            r.id,parent,scope->get_type_code(),scope->file_idx,scope->lineno,
            scope->def_file_idx,scope->def_lineno,unsigned(scope->is_cell),
            int(scope->time_units),int(scope->time_precision))<0)return -1;
        if(fprintf(out,"VSM_NAME %zu ",r.name_bytes)<0)return -1;
        for(size_t i=0;i<r.name_bytes;++i)if(fprintf(out,"%02x",(unsigned char)r.name[i])<0)return -1;
        if(fprintf(out,"\nVSM_DEFINITION %zu ",r.definition_bytes)<0)return -1;
        for(size_t i=0;i<r.definition_bytes;++i)if(fprintf(out,"%02x",(unsigned char)r.definition[i])<0)return -1;
        if(fprintf(out,"\nVSM_TIME %llu %llu %llu\n",
            scope->scoped_time.scope?r.id:0,scope->scoped_stime.scope?r.id:0,
            scope->scoped_realtime.scope?r.id:0)<0)return -1;
        auto fun=dynamic_cast<vpiScopeFunction*>(scope);
        if(fun && fprintf(out,"VSM_FUNCTION %d %u %u\n",fun->vpi_get(vpiFuncType),
            fun->get_func_width(),unsigned(fun->get_func_init_val()))<0)return -1;
        if(fprintf(out,"VSM_INTERN %zu\n",scope->intern.size())<0)return -1;
        for(auto item:scope->intern)if(fprintf(out,"VSM_OBJECT %llu %d\n",
            robotron_object_ids.at(item),robotron_object_types.at(item))<0)return -1;
    }
    return fprintf(out,"VSM_END %zu\n",scopes.size())<0 || ferror(out)?-1:0;
}

// Allocation identity bridge, distinct from current ordered intern membership.
// Includes registered objects omitted by a fault; never dereferences those objects.
extern "C" int robotron_vvp_scope_metadata_reference_inventory(FILE* out)
{
    vector<__vpiScope*> scopes;
    if(!out || robotron_scope_metadata_validate(scopes))return -1;
    map<unsigned long long,vpiHandle> objects;
    for(auto entry:robotron_object_ids)objects[entry.second]=entry.first;
    if(fprintf(out,"VSMR_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
    for(size_t i=0;i<scopes.size();++i) {
        auto scope=scopes[i];const auto& r=robotron_scope_metadata.at(scope);
        if(fprintf(out,"VSMR_SCOPE %llu %p %zu\n",r.id,(void*)scope,i+1)<0)return -1;
    }
    for(auto entry:objects)if(fprintf(out,"VSMR_OBJECT %llu %p %d\n",entry.first,
        (void*)entry.second,robotron_object_types.at(entry.second))<0)return -1;
    return fprintf(out,"VSMR_END %zu %zu\n",scopes.size(),objects.size())<0 || ferror(out)?-1:0;
}

// Exact previous-image reuse: every call still runs the complete native scan.
// Only the timestamp header is separated; every remaining byte is compared.
#include <string>
static int robotron_scope_compact(FILE*out,int(*inventory)(FILE*),const char*tag,
                                  std::string& previous,unsigned long long& sequence)
{
    if(!out || sequence==~0ULL)return -1;
    char*data=0;size_t size=0;FILE*stream=open_memstream(&data,&size);
    if(!stream)return -1;
    int rc=inventory(stream);int close_rc=fclose(stream);
    if(rc || close_rc){free(data);return -1;}
    const char*end=(const char*)memchr(data,'\n',size);
    if(!end){free(data);return -1;}
    std::string body(end+1,size-(end+1-data));free(data);
    bool full=!sequence || body!=previous;
    if(fprintf(out,"%s_BEGIN 1 %llu %llu %u %zu\n",tag,
        (unsigned long long)schedule_simtime(),sequence+1,unsigned(full),body.size())<0)return -1;
    if(full && fwrite(body.data(),1,body.size(),out)!=body.size())return -1;
    if(fprintf(out,"%s_END\n",tag)<0 || ferror(out))return -1;
    previous.swap(body);++sequence;return 0;
}
extern "C" int robotron_vvp_scope_metadata_compact_inventory(FILE*out)
{
    static std::string previous;static unsigned long long sequence=0;
    return robotron_scope_compact(out,robotron_vvp_scope_metadata_inventory,"VSMD",previous,sequence);
}
extern "C" int robotron_vvp_scope_metadata_reference_compact_inventory(FILE*out)
{
    static std::string previous;static unsigned long long sequence=0;
    return robotron_scope_compact(out,robotron_vvp_scope_metadata_reference_inventory,"VSMRD",previous,sequence);
}

// Paired diagnostic faults. Restoration does not traverse the corrupted graph.
extern "C" int robotron_vvp_scope_metadata_toggle(unsigned field)
{
    static __vpiScope* saved=0;static unsigned saved_field=0;
    static vpiHandle saved_item=0;
    if(field>5 || (saved && field!=saved_field))return -1;
    bool restoring=saved!=0;__vpiScope*scope=saved;
    if(!restoring){
        vector<__vpiScope*> scopes;if(robotron_scope_metadata_validate(scopes))return -1;
        for(auto item:scopes) {
            if(field>=2 && field<=4){if(typeid(*item)==typeid(vpiScopeFunction)){scope=item;break;}}
            else if(typeid(*item)==typeid(vpiScopeModule) && !item->intern.empty()){scope=item;break;}
        }
        if(!scope)return -1;
    }
    if(field==0)scope->time_units=int(scope->time_units)^1;
    else if(field==1)scope->lineno^=1;
    else if(field<=4)static_cast<vpiScopeFunction*>(scope)->robotron_metadata_fault(field);
    else if(restoring)scope->intern.front()=saved_item;
    else {saved_item=scope->intern.front();scope->intern.front()=reinterpret_cast<vpiHandle>(1);}
    if(restoring){saved=0;saved_item=0;}else{saved=scope;saved_field=field;}
    return 1;
}

extern "C" unsigned long long robotron_vvp_net_handle_id(const void*);
extern "C" int robotron_vvp_port_payload_inventory(FILE*out)
{
    vector<__vpiScope*> scopes;
    if(!out || robotron_scope_metadata_validate(scopes))return -1;
    map<vpiHandle,__vpiScope*> owners;
    for(auto scope:scopes)for(auto item:scope->intern)
        if(!owners.insert({item,scope}).second)return -1;
    map<unsigned long long,vpiPortInfo*> ports;
    set<vpiPortBitInfo*> seen;
    for(auto entry:robotron_ports){
        auto port=entry.first;const auto&reg=entry.second;
        auto owner=owners.find(port);auto id=robotron_object_ids.find(port);
        if(typeid(*port)!=typeid(vpiPortInfo) || !reg.ready ||
           owner==owners.end() || id==robotron_object_ids.end() ||
           port->robotron_parent()!=owner->second || port->robotron_name()!=reg.name ||
           !reg.name || !reg.bytes || port->get_width()<0 ||
           size_t(port->get_width())!=port->port_bits_.size())return -1;
        if(port->get_port() && !robotron_vvp_net_handle_id(port->get_port()))return -1;
        for(auto bit:port->port_bits_){
            // Registry membership is checked before any cast, virtual call or dereference.
            if(!robotron_port_bits.count(bit) || !seen.insert(bit).second)return -1;
            auto bit_owner=owners.find(bit);
            if(typeid(*bit)!=typeid(vpiPortBitInfo) || bit_owner==owners.end() ||
               bit_owner->second!=owner->second || !robotron_object_ids.count(bit) ||
               bit->vpi_handle(vpiParent)!=port)return -1;
        }
        ports[id->second]=port;
    }
    if(seen.size()!=robotron_port_bits.size())return -1;
    if(fprintf(out,"VPP_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
    for(auto entry:ports){
        auto port=entry.second;const auto&reg=robotron_ports.at(port);
        if(fprintf(out,"VPP_PORT %llu %p %llu %u %d %d %p %llu %zu\n",entry.first,(void*)port,
            robotron_scope_metadata.at(port->robotron_parent()).id,port->get_index(),port->get_direction(),
            port->get_width(),(void*)port->get_port(),port->get_port()?robotron_vvp_net_handle_id(port->get_port()):0,
            reg.bytes)<0)return -1;
        if(fputs("VPP_NAME ",out)==EOF)return -1;
        for(size_t i=0;i<reg.bytes;++i)if(fprintf(out,"%02x",(unsigned char)reg.name[i])<0)return -1;
        if(fputc('\n',out)==EOF)return -1;
        for(auto bit:port->port_bits_)if(fprintf(out,"VPP_BIT %llu %p %u\n",
            robotron_object_ids.at(bit),(void*)bit,bit->get_bit())<0)return -1;
    }
    return fprintf(out,"VPP_END %zu %zu\n",ports.size(),seen.size())<0 || ferror(out)?-1:0;
}

// Diagnostic only: validate before injection, restore without traversing bad fields.
extern "C" int robotron_vvp_port_payload_toggle(unsigned field)
{
    static vpiPortInfo* saved=0;static unsigned saved_field=0;
    if(field>8 || (saved && field!=saved_field))return -1;
    bool restoring=saved!=0;auto port=saved;
    if(!restoring){
        char*data=0;size_t size=0;FILE*out=open_memstream(&data,&size);
        if(!out)return -1;
        int rc=robotron_vvp_port_payload_inventory(out);int close_rc=fclose(out);free(data);
        if(rc || close_rc)return -1;
        unsigned long long first=~0ULL;
        for(auto entry:robotron_ports)if(!entry.first->port_bits_.empty()){
            auto id=robotron_object_ids.at(entry.first);
            if(id<first){first=id;port=entry.first;}
        }
        if(!port)return -1;
    }
    if(field==8)robotron_ports.at(port).ready=!robotron_ports.at(port).ready;
    else if(field==2 || field==7)port->port_bits_.front()->robotron_payload_fault(field);
    else port->robotron_payload_fault(field);
    if(restoring)saved=0;else{saved=port;saved_field=field;}
    return 1;
}

// Complete initialized intern ownership, without supplied-pointer dereferences.
extern "C" int robotron_vvp_scope_object_owners(std::map<const void*,const void*>*owners)
{
    vector<__vpiScope*> scopes;
    if(!owners || robotron_scope_metadata_validate(scopes))return -1;
    std::map<const void*,const void*> result;
    for(auto scope:scopes)for(auto item:scope->intern)
        if(!result.insert({item,scope}).second)return -1;
    owners->swap(result);return 0;
}

extern "C" int robotron_vvp_parameter_owners(std::map<const void*,std::pair<unsigned long long,const void*>>*owners)
{
    vector<__vpiScope*> scopes;
    if(!owners||robotron_scope_metadata_validate(scopes))return -1;
    std::map<const void*,std::pair<unsigned long long,const void*>> result;
    for(auto scope:scopes)for(auto item:scope->intern)if(robotron_object_types.at(item)==vpiParameter)
        if(!result.insert({item,{robotron_object_ids.at(item),scope}}).second)return -1;
    owners->swap(result);return 0;
}

extern "C" int robotron_vvp_memory_owners(std::map<const void*,std::pair<unsigned long long,const void*>>*owners)
{
    vector<__vpiScope*> scopes;
    if(!owners||robotron_scope_metadata_validate(scopes))return -1;
    std::map<const void*,std::pair<unsigned long long,const void*>> result;
    for(auto scope:scopes)for(auto item:scope->intern)if(robotron_object_types.at(item)==vpiMemory)
        if(!result.insert({item,{robotron_object_ids.at(item),scope}}).second)return -1;
    owners->swap(result);return 0;
}

extern "C" void robotron_vvp_memory_forget(vpiHandle object)
{
    // Erase identities before a stale intern entry can be traversed. Do not
    // mutate the native scope vector during its own teardown iteration.
    robotron_attached_objects.erase(object);
    robotron_object_ids.erase(object);
    robotron_object_types.erase(object);
}
