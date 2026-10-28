#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
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

/*
 * Callbacks are objects that carry a function to be called when some
 * event in the simulation occurs. The VPI code create a __vpiCallback
 * object, and that object is put in some location that the simulation
 * can look when the event in question is tripped.
 */

# include  "vpi_user.h"
# include  "vpi_priv.h"
# include  "vvp_net.h"
# include  "schedule.h"
# include  "event.h"
# include  "vvp_net_sig.h"
# include  "config.h"
#ifdef CHECK_WITH_VALGRIND
#include  "vvp_cleanup.h"
#endif
# include  <cstdio>
# include  <cassert>
# include  <cstdlib>
# include  <map>
# include  <set>
# include  <cstdint>
# include  <dlfcn.h>

using namespace std;

static const char*cb_reason_name(PLI_INT32 reason)
{
      switch (reason) {
	  case cbValueChange:
	    return "cbValueChange";
	  case cbStmt:
	    return "cbStmt";
	  case cbForce:
	    return "cbForce";
	  case cbRelease:
	    return "cbRelease";
	  case cbAtStartOfSimTime:
	    return "cbAtStartOfSimTime";
	  case cbReadWriteSynch:
	    return "cbReadWriteSynch";
	  case cbReadOnlySynch:
	    return "cbReadOnlySynch";
	  case cbNextSimTime:
	    return "cbNextSimTime";
	  case cbAfterDelay:
	    return "cbAfterDelay";
	  case cbEndOfCompile:
	    return "cbEndOfCompile";
	  case cbStartOfSimulation:
	    return "cbStartOfSimulation";
	  case cbEndOfSimulation:
	    return "cbEndOfSimulation";
	  case cbError:
	    return "cbError";
	  case cbTchkViolation:
	    return "cbTchkViolation";
	  case cbStartOfSave:
	    return "cbStartOfSave";
	  case cbEndOfSave:
	    return "cbEndOfSave";
	  case cbStartOfRestart:
	    return "cbStartOfRestart";
	  case cbEndOfRestart:
	    return "cbEndOfRestart";
	  case cbStartOfReset:
	    return "cbStartOfReset";
	  case cbEndOfReset:
	    return "cbEndOfReset";
	  case cbEnterInteractive:
	    return "cbEnterInteractive";
	  case cbExitInteractive:
	    return "cbExitInteractive";
	  case cbInteractiveScopeChange:
	    return "cbInteractiveScopeChange";
	  case cbUnresolvedSystf:
	    return "cbUnresolvedSystf";
	  case cbAtEndOfSimTime:
	    return "cbAtEndOfSimTime";
	  default:
	    return "unrecognised";
      }
}

static bool check_callback_time(p_cb_data data, bool allow_suppress)
{
      assert(data);
      if (!data->time) {
	    if (!allow_suppress) {
		  fprintf(stderr, "VPI error: null value passed in cb_data.time "
				  "when registering %s callback\n.",
				  cb_reason_name(data->reason));
		  return false;
	    }
	    return true;
      }
      switch (data->time->type) {
	  case vpiSimTime:
	    break;
	  case vpiScaledRealTime:
	    break;
	  case vpiSuppressTime:
	    if (!allow_suppress) {
		  fprintf(stderr, "VPI error: vpiSuppressTime is not valid "
				  "when registering %s callback\n.",
				  cb_reason_name(data->reason));
		  return false;
	    }
	    break;
	  default:
	    fprintf(stderr, "VPI error: invalid type passed in cb_data time "
			    "structure when registering %s callback\n.",
			    cb_reason_name(data->reason));
	    return false;
      }
      return true;
}

static void set_callback_time(p_cb_data data)
{
      assert(data && data->time);
      data->time->low  = 0;
      data->time->high = 0;
      data->time->real = 0.0;
      switch (data->time->type) {
	  case vpiSimTime:
	    vpip_time_to_timestruct(data->time, schedule_simtime());
	    break;
	  case vpiScaledRealTime:
	    data->time->real = vpip_scaled_time_from_handle(schedule_simtime(), data->obj);
	    break;
	  case vpiSuppressTime:
	    break;
	  default:
	    assert(0);
	    break;
      }
}

/*
 * Callback handles are created when the VPI function registers a
 * callback. The handle is stored by the run time, and it triggered
 * when the run-time thing that it is waiting for happens.
 *
 * This is the thing that the VPI code references by the vpiHandle. It
 * also points to callback data that the caller attached to the event,
 * as well as the time structure to receive data.
 *
 * The cb_sync is a private member that points to the schedulable
 * event that is triggered when the event happens. The sync_cb class
 * represents the action to execute when the scheduler gets to this
 * event. This member is only used for things like cbReadOnlySync.
 */

class sync_callback;

struct sync_cb  : public vvp_gen_event_s {
      sync_callback*handle;
      bool sync_flag;

      ~sync_cb () override { }

      virtual void run_run() override;
};

inline __vpiCallback::__vpiCallback()
{
      next = 0;
}

__vpiCallback::~__vpiCallback()
{
}

int __vpiCallback::get_type_code(void) const
{ return vpiCallback; }


/* Register object lifetime without inspecting optional callback fields. */
struct robotron_value_entry {
      value_callback *callback;
      uint64_t id;
      PLI_INT32 (*function)(p_cb_data);
      vpiHandle object;
      vvp_vpi_callback *owner;
      bool list_admitted;
};
static std::map<const void*,robotron_value_entry> robotron_value_live;
static uint64_t robotron_value_serial;

static void robotron_value_created(value_callback *cb, p_cb_data data)
{
      robotron_value_entry entry = {cb, ++robotron_value_serial,
                                    data->cb_rtn, data->obj, 0, false};
      robotron_value_live[cb] = entry;
}

value_callback::~value_callback()
{
      robotron_value_live.erase(this);
}

/* Never follow a supplied handle or an unregistered next pointer. */
int vvp_vpi_callback::robotron_value_contains(const value_callback *wanted) const
{
      const void *cursor = vpi_callbacks_;
      std::set<const void*> seen;
      unsigned found = 0;
      while (cursor) {
            auto it = robotron_value_live.find(cursor);
            if (it == robotron_value_live.end() || !seen.insert(cursor).second ||
                it->second.owner != this) return -1;
            const value_callback *cb = it->second.callback;
            if (cb == wanted) ++found;
            cursor = cb->next;
      }
      return found == 1 ? 1 : 0;
}

extern "C" unsigned long long robotron_vvp_value_identity(
      const void *handle, PLI_INT32 (*function)(p_cb_data),
      PLI_BYTE8 *user, vpiHandle object)
{
      auto it = robotron_value_live.find(handle);
      if (it == robotron_value_live.end() || !function || !user || !object) return 0;
      const robotron_value_entry &entry = it->second;
      if (entry.function != function || entry.object != object || !entry.owner) return 0;
      const value_callback *cb = entry.callback;
      /* user_data is initialized by the explicitly identified caller. */
      if (cb->cb_data.cb_rtn != function || cb->cb_data.obj != object ||
          cb->cb_data.user_data != user || cb->cb_data.reason != cbValueChange ||
          cb->cb_data.time != &cb->cb_time || cb->cb_data.value != &cb->cb_value ||
          cb->cb_time.type != vpiSuppressTime || cb->cb_value.format != vpiVectorVal ||
          entry.owner->robotron_value_contains(cb) != 1) return 0;
      /* index, suppressed time words and the temporary value union are unused. */
      return entry.id;
}

/* Explicit handoff proves the known caller initialized optional user_data.
 * This does not admit subclasses or authorize reading their retained history. */
extern "C" unsigned long long robotron_vvp_callback_list_admit(
    const void* handle,PLI_INT32(*function)(p_cb_data),PLI_BYTE8* user,vpiHandle object)
{
    auto it=robotron_value_live.find(handle);
    if(it==robotron_value_live.end() || typeid(*it->second.callback)!=typeid(value_callback))return 0;
    auto id=robotron_vvp_value_identity(handle,function,user,object);
    if(id)it->second.list_admitted=true;
    return id;
}

static struct {
      value_callback *callback;
      int field;
      const PLI_BYTE8 *user;
      vpiHandle object;
      PLI_INT32 (*function)(p_cb_data);
      __vpiCallback *next;
} robotron_value_fault = {};

extern "C" int robotron_vvp_value_toggle(
      const void *handle, PLI_INT32 (*function)(p_cb_data),
      PLI_BYTE8 *user, vpiHandle object, int field)
{
      auto it = robotron_value_live.find(handle);
      if (it == robotron_value_live.end() || field<0 || field>3 ||
          it->second.function != function || it->second.object != object) return -1;
      value_callback *cb = it->second.callback;
      if (robotron_value_fault.callback) {
            if (robotron_value_fault.callback != cb || robotron_value_fault.field != field) return -1;
            cb->cb_data.user_data = robotron_value_fault.user;
            cb->cb_data.obj = robotron_value_fault.object;
            cb->cb_data.cb_rtn = robotron_value_fault.function;
            cb->next = robotron_value_fault.next;
            robotron_value_fault.callback = 0;
            return 1;
      }
      if (!robotron_vvp_value_identity(handle,function,user,object)) return -1;
      robotron_value_fault.callback = cb;
      robotron_value_fault.field = field;
      robotron_value_fault.user = cb->cb_data.user_data;
      robotron_value_fault.object = cb->cb_data.obj;
      robotron_value_fault.function = cb->cb_data.cb_rtn;
      robotron_value_fault.next = cb->next;
      switch (field) {
        case 0: cb->cb_data.user_data = 0; break;
        case 1: cb->cb_data.obj = (vpiHandle)(uintptr_t)1; break;
        case 2: cb->cb_data.cb_rtn = 0; break;
        case 3: cb->next = (__vpiCallback*)(uintptr_t)1; break;
      }
      return 1;
}

value_callback::value_callback(p_cb_data data)
{
      cb_data = *data;
      if (data->time) {
	    cb_time = *(data->time);
      } else {
	    cb_time.type = vpiSuppressTime;
      }
      cb_data.time = &cb_time;
      if (data->value) {
	    cb_value = *(data->value);
      } else {
	    cb_value.format = vpiSuppressVal;
      }
      cb_data.value = &cb_value;
      robotron_value_created(this, data);
}

/*
 * Normally, any assign to a value triggers a value change callback,
 * so return a constant true here. This is a stub.
 */
bool value_callback::test_value_callback_ready(void)
{
      return true;
}

static void vpip_real_value_change(value_callback*cbh, vpiHandle ref)
{
      struct __vpiRealVar*rfp = dynamic_cast<__vpiRealVar*>(ref);
      assert(rfp);
      vvp_vpi_callback*obj = dynamic_cast<vvp_vpi_callback*>(rfp->net->fil);
      assert(obj);

      obj->add_vpi_callback(cbh);
}

class value_part_callback : public value_callback {
    public:
      explicit value_part_callback(p_cb_data data);
      ~value_part_callback() override;

      value_part_callback(const value_part_callback&) = delete;
      value_part_callback& operator=(const value_part_callback&) = delete;

      bool test_value_callback_ready(void) override;

    private:
      char*value_bits_;
      size_t value_off_;
};

inline value_part_callback::value_part_callback(p_cb_data data)
: value_callback(data)
{
      struct __vpiPV*pobj = dynamic_cast<__vpiPV*>(data->obj);
      assert(pobj);

      vvp_vpi_callback*sig_fil;
      sig_fil = dynamic_cast<vvp_vpi_callback*>(pobj->net->fil);
      assert(sig_fil);

      sig_fil->add_vpi_callback(this);
	// Get a reference value that can be used to compare with an
	// updated value. Use the filter get_value to get the value,
	// and get it in BinStr form so that compares are easy. Note
	// that the vpiBinStr format has the MSB first, but the tbase
	// is lsb first.
      s_vpi_value tmp_value;
      tmp_value.format = vpiBinStrVal;
      sig_fil->get_value(&tmp_value);

      value_bits_ = new char[pobj->width+1];
      value_off_ = pobj->parent->vpi_get(vpiSize) - pobj->width - pobj->tbase;

      memcpy(value_bits_, tmp_value.value.str + value_off_, pobj->width);
      value_bits_[pobj->width] = 0;
}

value_part_callback::~value_part_callback()
{
      delete[]value_bits_;
}

bool value_part_callback::test_value_callback_ready(void)
{
      struct __vpiPV*pobj = dynamic_cast<__vpiPV*>(cb_data.obj);
      assert(pobj);

      vvp_vpi_callback*sig_fil;
      sig_fil = dynamic_cast<vvp_vpi_callback*>(pobj->net->fil);
      assert(sig_fil);

	// Get a reference value that can be used to compare with an
	// updated value.
      s_vpi_value tmp_value;
      tmp_value.format = vpiBinStrVal;
      sig_fil->get_value(&tmp_value);

      if (memcmp(value_bits_, tmp_value.value.str + value_off_, pobj->width) == 0)
	    return false;

      memcpy(value_bits_, tmp_value.value.str + value_off_, pobj->width);
      return true;
}

/*
 * Attach the __vpiCallback to the object that this part select
 * selects from. The part select itself is not a vvp_vpi_callback
 * object, but it refers to a net that is a vvp_vpi_callback, so
 * add the callback to that object.
 */
static value_callback*make_value_change_part(p_cb_data data)
{
	/* Attach the __vpiCallback object to the signal. */
      value_callback*cbh = new value_part_callback(data);
      return cbh;
}

/*
 * A value change callback is tripped when a bit of a signal
 * changes. This function creates that value change callback and
 * attaches it to the relevant vpiSignal object. Also, if the signal
 * does not already have them, create some callback functors to do the
 * actual value change detection.
 */
static value_callback* make_value_change(p_cb_data data)
{
      if (!check_callback_time(data, true))
	    return 0;

      if (vpi_get(vpiAutomatic, data->obj)) {
            fprintf(stderr, "vpi error: cannot place value change "
                            "callback on automatically allocated "
                            "variable '%s'\n",
                            vpi_get_str(vpiName, data->obj));
            return 0;
      }

	// Special case: the target object is a vpiPartSelect
      if (data->obj->get_type_code() == vpiPartSelect) {
            if (data->obj->vpi_handle(vpiArray))
	        return vpip_array_word_change(data);
            else
	        return make_value_change_part(data);
      }

      if (data->obj->get_type_code() == vpiMemoryWord)
	    return vpip_array_word_change(data);

      if (data->obj->get_type_code() == vpiMemory)
	    return vpip_array_change(data);

      value_callback*obj = new value_callback(data);

      assert(data->obj);
      switch (data->obj->get_type_code()) {

	  case vpiReg:
	  case vpiNet:
	  case vpiIntegerVar:
	  case vpiBitVar:
	  case vpiByteVar:
	  case vpiShortIntVar:
	  case vpiIntVar:
	  case vpiLongIntVar:
	      /* Attach the callback to the vvp_fun_signal node by
		 putting it in the vpi_callbacks list. */
	    struct __vpiSignal*sig;
	    sig = dynamic_cast<__vpiSignal*>(data->obj);

	    vvp_net_fil_t*sig_fil;
	    sig_fil = dynamic_cast<vvp_net_fil_t*>(sig->node->fil);
	    assert(sig_fil);

	      /* Attach the __vpiCallback object to the signal. */
	    sig_fil->add_vpi_callback(obj);
	    break;

	  case vpiRealVar:
	    vpip_real_value_change(obj, data->obj);
	    break;

	  case vpiNamedEvent:
	    __vpiNamedEvent*nev;
	    nev = dynamic_cast<__vpiNamedEvent*>(data->obj);
	    nev->add_vpi_callback(obj);
	    break;

	  case vpiModule:
	  case vpiConstant:
	  case vpiParameter:
	      /* These are constant, so there are no value change
		 lists to put them in. */
	    break;

	  default:
	    fprintf(stderr, "make_value_change: sorry: I cannot callback "
		    "values on type code=%d\n",
		    data->obj->get_type_code());
	    delete obj;
	    return 0;
      }

      return obj;
}

class sync_callback : public __vpiCallback {
    public:
      explicit sync_callback(p_cb_data data);
      ~sync_callback() override;

      sync_callback(const sync_callback&) = delete;
      sync_callback& operator=(const sync_callback&) = delete;

    public:
	// scheduled event
      struct sync_cb* cb_sync;
	// user supplied callback data
      struct t_vpi_time cb_time;

    private:
};

/* Opt-in observation of live synchronization callback headers. Registry IDs
 * identify lifetimes without exposing allocation addresses. This does not
 * serialize arbitrary user data, object/value referents or the C++ stack. */
static std::map<unsigned long long, sync_callback*> robotron_sync_live;
typedef PLI_INT32 (*robotron_callback_fn)(p_cb_data);
static std::map<const sync_callback*, robotron_callback_fn> robotron_sync_functions;
static unsigned long long robotron_sync_sequence = 0;
static sync_callback* robotron_sync_executing = 0;

inline sync_callback::sync_callback(p_cb_data data)
{
      cb_sync = 0;

      cb_data = *data;
      assert(data->time);
      cb_time = *(data->time);
      cb_data.time = &cb_time;
      robotron_sync_live[++robotron_sync_sequence] = this;
      robotron_sync_functions[this] = cb_data.cb_rtn;
}

sync_callback::~sync_callback()
{
      robotron_sync_functions.erase(this);
      for (auto it = robotron_sync_live.begin(); it != robotron_sync_live.end(); ++it)
          if (it->second == this) { robotron_sync_live.erase(it); break; }
      delete cb_sync;
}

void sync_cb::run_run()
{
      if (handle == 0)
	    return;

      sync_callback*cur = handle;

	/* Run the callback. If the cb_rtn function pointer is set to
	   null, then just skip the whole thing and free it. This is
	   the usual way to cancel one-time callbacks of this sort. */
      if (cur->cb_data.cb_rtn != 0) {
	    set_callback_time(&cur->cb_data);
	    assert(vpi_mode_flag == VPI_MODE_NONE);
	    vpi_mode_flag = sync_flag? VPI_MODE_ROSYNC : VPI_MODE_RWSYNC;
	    sync_callback* previous = robotron_sync_executing;
            robotron_sync_executing = cur;
            (cur->cb_data.cb_rtn)(&cur->cb_data);
            robotron_sync_executing = previous;
	    vpi_mode_flag = VPI_MODE_NONE;
      }

      delete cur;
}

static vvp_time64_t get_sync_cb_time(sync_callback*obj)
{
      vvp_time64_t tv = 0;
      switch (obj->cb_time.type) {
	  case vpiSimTime:
	    tv = vpip_timestruct_to_time(&obj->cb_time);
	    break;

	  case vpiScaledRealTime:
	    tv = vpip_scaled_real_to_time64(obj->cb_time.real,
		     vpip_timescale_scope_from_handle(obj->cb_data.obj));
	    break;

	  default:
	    fprintf(stderr, "get_sync_cb_time: Unsupported time type %d.\n",
	            (int)obj->cb_time.type);
	    assert(0);
	    break;
      }
      return tv;
}

static sync_callback* make_sync(p_cb_data data, bool readonly_flag)
{
      if (!check_callback_time(data, false))
	    return 0;

      sync_callback*obj = new sync_callback(data);

      struct sync_cb*cb = new sync_cb;
      cb->sync_flag = readonly_flag? true : false;
      cb->handle = obj;
      obj->cb_sync = cb;

      vvp_time64_t tv = get_sync_cb_time(obj);
      schedule_generic(cb, tv, true, readonly_flag);

      return obj;
}

static struct __vpiCallback* make_afterdelay(p_cb_data data)
{
      if (!check_callback_time(data, false))
	    return 0;

      sync_callback*obj = new sync_callback(data);
      struct sync_cb*cb = new sync_cb;
      cb->sync_flag = false;
      cb->handle = obj;
      obj->cb_sync = cb;

      vvp_time64_t tv = get_sync_cb_time(obj);
      schedule_generic(cb, tv, false);

      return obj;
}

static struct __vpiCallback* make_at_start_of_sim_time(p_cb_data data)
{
      if (!check_callback_time(data, false))
	    return 0;

      sync_callback*obj = new sync_callback(data);
      struct sync_cb*cb = new sync_cb;
      cb->sync_flag = false;
      cb->handle = obj;
      obj->cb_sync = cb;

      vvp_time64_t tv = get_sync_cb_time(obj);
      vvp_time64_t cur = schedule_simtime();
      if (cur > tv) {
	    tv = 0;
	    assert(0);
      } else if (cur == tv) {
	    tv = 0;
      } else {
	    tv -= cur;
      }
      schedule_at_start_of_simtime(cb, tv);

      return obj;
}

static struct __vpiCallback* make_at_end_of_sim_time(p_cb_data data)
{
      if (!check_callback_time(data, false))
	    return 0;

      sync_callback*obj = new sync_callback(data);
      struct sync_cb*cb = new sync_cb;
      cb->sync_flag = false;
      cb->handle = obj;
      obj->cb_sync = cb;

      vvp_time64_t tv = get_sync_cb_time(obj);
      vvp_time64_t cur = schedule_simtime();
      if (cur > tv) {
	    tv = 0;
	    assert(0);
      } else if (cur == tv) {
	    tv = 0;
      } else {
	    tv -= cur;
      }
      schedule_at_end_of_simtime(cb, tv);

      return obj;
}

/*
 * The following functions are the used for pre and post simulation
 * callbacks.
 */

class simulator_callback;
struct robotron_start_record {
    unsigned long long id;
    PLI_INT32 (*function)(p_cb_data);
};
static std::map<const simulator_callback*, robotron_start_record> robotron_start_live;
static unsigned long long robotron_start_serial = 0;
static simulator_callback* robotron_start_active = 0;
static __vpiCallback* robotron_start_active_next = 0;

class simulator_callback : public __vpiCallback {
    public:
      explicit simulator_callback(const struct t_cb_data*data);
      ~simulator_callback() override { robotron_start_live.erase(this); }

    public:
      struct t_vpi_time cb_time;
};

inline simulator_callback::simulator_callback(const struct t_cb_data*data)
{
      cb_data = *data;
      if ((data->reason == cbNextSimTime) && data->time) {
	    cb_time = *(data->time);
      } else if (data->reason == cbEndOfSimulation) {
	    cb_time.type = vpiSimTime;
      } else {
	    cb_time.type = vpiSuppressTime;
      }
      cb_data.time = &cb_time;
      if (data->reason == cbStartOfSimulation)
          robotron_start_live[this] = {++robotron_start_serial, data->cb_rtn};
}

static simulator_callback*NextSimTime = 0;
static simulator_callback*EndOfCompile = 0;
static simulator_callback*StartOfSimulation = 0;
static simulator_callback*EndOfSimulation = 0;

#ifdef CHECK_WITH_VALGRIND
/* This is really only needed if the simulator aborts before starting the
 * main event loop. For that reason we can skip the next sim time queue. */
void simulator_cb_delete(void)
{
      simulator_callback* cur;

	/* Delete all the end of compile callbacks. */
      while (EndOfCompile) {
	    cur = EndOfCompile;
	    EndOfCompile = dynamic_cast<simulator_callback*>(cur->next);
	    delete cur;
      }

	/* Delete all the start of simulation callbacks. */
      while (StartOfSimulation) {
	    cur = StartOfSimulation;
	    StartOfSimulation = dynamic_cast<simulator_callback*>(cur->next);
	    delete cur;
      }

	/* Delete all the end of simulation callbacks. */
      while (EndOfSimulation) {
	    cur = EndOfSimulation;
	    EndOfSimulation = dynamic_cast<simulator_callback*>(cur->next);
	    delete cur;
      }
}
#endif

void vpiEndOfCompile(void) {
      simulator_callback* cur;

      /*
       * Walk the list of register callbacks, executing them and
       * freeing them when done.
       */
      assert(vpi_mode_flag == VPI_MODE_NONE);
      vpi_mode_flag = VPI_MODE_RWSYNC;

      while (EndOfCompile) {
	    cur = EndOfCompile;
	    EndOfCompile = dynamic_cast<simulator_callback*>(cur->next);
	    if (cur->cb_data.cb_rtn != 0) {
		  (cur->cb_data.cb_rtn)(&cur->cb_data);
	    }
	    delete cur;
      }

      vpi_mode_flag = VPI_MODE_NONE;
}

void vpiStartOfSim(void) {
      simulator_callback* cur;
      assert(!robotron_start_active);

      /*
       * Walk the list of register callbacks, executing them and
       * freeing them when done.
       */
      assert(vpi_mode_flag == VPI_MODE_NONE);
      vpi_mode_flag = VPI_MODE_RWSYNC;

      while (StartOfSimulation) {
	    cur = StartOfSimulation;
	    StartOfSimulation = dynamic_cast<simulator_callback*>(cur->next);
            robotron_start_active = cur;
            robotron_start_active_next = cur->next;
	    if (cur->cb_data.cb_rtn != 0) {
		  (cur->cb_data.cb_rtn)(&cur->cb_data);
	    }
            robotron_start_active = 0;
            robotron_start_active_next = 0;
	    delete cur;
      }

      vpi_mode_flag = VPI_MODE_NONE;
}

void vpiPostsim(void) {
      simulator_callback* cur;

      /*
       * Walk the list of register callbacks
       */
      assert(vpi_mode_flag == VPI_MODE_NONE);
      vpi_mode_flag = VPI_MODE_ROSYNC;

      while (EndOfSimulation) {
	    cur = EndOfSimulation;
	    EndOfSimulation = dynamic_cast<simulator_callback*>(cur->next);
	    if (cur->cb_data.cb_rtn != 0) {
		  set_callback_time(&cur->cb_data);
		  (cur->cb_data.cb_rtn)(&cur->cb_data);
	    }
	    delete cur;
      }

      vpi_mode_flag = VPI_MODE_NONE;
}

/*
 * The scheduler invokes this to clear out callbacks for the next
 * simulation time.
 */
void vpiNextSimTime(void)
{
      simulator_callback* cur;
      simulator_callback* next = NextSimTime;
      NextSimTime = 0;

      assert(vpi_mode_flag == VPI_MODE_NONE);
      vpi_mode_flag = VPI_MODE_RWSYNC;

      while (next) {
            cur = next;
            next = dynamic_cast<simulator_callback*>(cur->next);
            if (cur->cb_data.cb_rtn != 0) {
                  set_callback_time(&cur->cb_data);
                  (cur->cb_data.cb_rtn)(&cur->cb_data);
            }
            delete cur;
      }

      vpi_mode_flag = VPI_MODE_NONE;
}

static simulator_callback* make_prepost(p_cb_data data)
{
      if ((data->reason == cbNextSimTime) && !check_callback_time(data, true))
	    return 0;

      simulator_callback*obj = new simulator_callback(data);

      /* Insert at head of list */
      switch (data->reason) {
	  case cbEndOfCompile:
	    obj->next = EndOfCompile;
	    EndOfCompile = obj;
	    break;
	  case cbStartOfSimulation:
	    obj->next = StartOfSimulation;
	    StartOfSimulation = obj;
	    break;
	  case cbEndOfSimulation:
	    obj->next = EndOfSimulation;
	    EndOfSimulation = obj;
	    break;
	  case cbNextSimTime:
	    obj->next = NextSimTime;
	    NextSimTime = obj;
	    break;
      }

      return obj;
}

vpiHandle vpi_register_cb(p_cb_data data)
{
      struct __vpiCallback*obj = 0;

      assert(data);
      switch (data->reason) {

	  case cbValueChange:
	    obj = make_value_change(data);
	    break;

	  case cbReadOnlySynch:
	    obj = make_sync(data, true);
	    break;

	  case cbReadWriteSynch:
	    obj = make_sync(data, false);
	    break;

	  case cbAtStartOfSimTime:
	    obj = make_at_start_of_sim_time(data);
	    break;

	  case cbAtEndOfSimTime:
	    obj = make_at_end_of_sim_time(data);
	    break;

	  case cbAfterDelay:
	    obj = make_afterdelay(data);
	    break;

	  case cbEndOfCompile:
	  case cbStartOfSimulation:
	  case cbEndOfSimulation:
	  case cbNextSimTime:
	    obj = make_prepost(data);
	    break;

	  default:
	    fprintf(stderr, "vpi error: vpi_register_cb invalid or "
		    "unsupported callback reason: %d\n",
		    (int)data->reason);
	    break;
      }

      return obj;
}

/*
 * Removing a callback doesn't really delete it right away. Instead,
 * it clears the reference to the user callback function. This causes
 * the callback to quietly reap itself.
 */
PLI_INT32 vpi_remove_cb(vpiHandle ref)
{
      struct __vpiCallback*obj = dynamic_cast<__vpiCallback*>(ref);
      assert(obj);
      obj->cb_data.cb_rtn = 0;

      return 1;
}

void callback_execute(struct __vpiCallback*cur)
{
      const vpi_mode_t save_mode = vpi_mode_flag;
      vpi_mode_flag = VPI_MODE_RWSYNC;

      assert(cur->cb_data.cb_rtn);
      set_callback_time(&cur->cb_data);
      (cur->cb_data.cb_rtn)(&cur->cb_data);

      vpi_mode_flag = save_mode;
}

/*
 * Usually there is at most one array word associated with a vvp signal, but
 * due to port collapsing, there may be more. Using a linked list to record
 * the array words minimises memory use for the most common case (no array
 * words) or next most common case (one array word).
 */
struct __vpi_array_word {
      struct __vpi_array_word* next;
      struct __vpiArray* array;
      unsigned long word;
};

struct robotron_callback_word_entry {
    unsigned long long id;
    vvp_vpi_callback* owner;
};
static std::map<vvp_vpi_callback*,unsigned long long>& robotron_callback_owners()
{static std::map<vvp_vpi_callback*,unsigned long long> value;return value;}
static std::map<__vpi_array_word*,robotron_callback_word_entry>& robotron_callback_words()
{static std::map<__vpi_array_word*,robotron_callback_word_entry> value;return value;}
static unsigned long long robotron_callback_owner_serial,robotron_callback_word_serial;
static unsigned robotron_callback_dispatch_depth;
struct robotron_callback_dispatch_guard {
    robotron_callback_dispatch_guard(){++robotron_callback_dispatch_depth;}
    ~robotron_callback_dispatch_guard(){--robotron_callback_dispatch_depth;}
};

vvp_vpi_callback::vvp_vpi_callback()
{
      vpi_callbacks_ = 0;
      array_words_ = 0;
      robotron_callback_owners()[this]=++robotron_callback_owner_serial;
}

vvp_vpi_callback::~vvp_vpi_callback()
{
      assert(vpi_callbacks_ == 0);
      assert(array_words_ == 0);
      robotron_callback_owners().erase(this);
}

void vvp_vpi_callback::attach_as_word(vvp_array_t arr, unsigned long addr)
{
      struct __vpi_array_word*tmp = new __vpi_array_word;
      tmp->array = arr;
      tmp->word = addr;
      tmp->next = array_words_;
      array_words_ = tmp;
      robotron_callback_words()[tmp]={++robotron_callback_word_serial,this};
}

void vvp_vpi_callback::add_vpi_callback(value_callback*cb)
{
      auto it = robotron_value_live.find(cb);
      assert(it != robotron_value_live.end() && !it->second.owner);
      it->second.owner = this;
      cb->next = vpi_callbacks_;
      vpi_callbacks_ = cb;
}

#ifdef CHECK_WITH_VALGRIND
void vvp_vpi_callback::clear_all_callbacks()
{
      while (vpi_callbacks_) {
	    value_callback *tmp = dynamic_cast<value_callback*>
	                            (vpi_callbacks_->next);
	    delete vpi_callbacks_;
	    vpi_callbacks_ = tmp;
      }
      while (array_words_) {
	    struct __vpi_array_word*tmp = array_words_->next;
	    robotron_callback_words().erase(array_words_);
	    delete array_words_;
	    array_words_ = tmp;
      }
}
#endif

/*
 * A vvp_fun_signal uses this method to run its callbacks whenever it
 * has a value change. If the cb_rtn is non-nil, then call the
 * callback function. If the cb_rtn pointer is nil, then the object
 * has been marked for deletion. Free it.
 */
void vvp_vpi_callback::run_vpi_callbacks()
{
      robotron_callback_dispatch_guard observation_guard;
      struct __vpi_array_word*array_word = array_words_;
      while (array_word) {
	    array_word->array->word_change(array_word->word);
	    array_word = array_word->next;
      }

      value_callback *next = vpi_callbacks_;
      value_callback *prev = 0;

      while (next) {
	    value_callback*cur = next;
	    next = dynamic_cast<value_callback*>(cur->next);

	    if (cur->cb_data.cb_rtn != 0) {
		  if (cur->test_value_callback_ready()) {
			if (cur->cb_data.value)
			      get_value(cur->cb_data.value);

			callback_execute(cur);
		  }
		  prev = cur;

	    } else if (prev == 0) {

		  vpi_callbacks_ = next;
		  cur->next = 0;
		  delete cur;

	    } else {
		  assert(prev->next == cur);
		  prev->next = next;
		  cur->next = 0;
		  delete cur;
	    }
      }
}

void vvp_signal_value::get_signal_value(struct t_vpi_value*vp)
{
      switch (vp->format) {
	  case vpiScalarVal:
	    // This works because vvp_bit4_t has the same encoding
	    // as a scalar value! See vpip_vec4_get_value() for a
	    // more robust method.
	    vp->value.scalar = value(0);
	    break;

	  case vpiBinStrVal:
	  case vpiOctStrVal:
	  case vpiDecStrVal:
	  case vpiHexStrVal:
	  case vpiIntVal:
	  case vpiVectorVal:
	  case vpiStringVal:
	  case vpiRealVal: {
	    unsigned wid = value_size();
	    vvp_vector4_t vec4(wid);
	    for (unsigned idx = 0; idx < wid; idx += 1) {
		  vec4.set_bit(idx, value(idx));
	    }
	    vpip_vec4_get_value(vec4, wid, false, vp);
	    break;
	  }

	  case vpiSuppressVal:
	    break;

	  default:
	    fprintf(stderr, "vpi_callback: value "
		    "format %d not supported (fun_signal)\n",
		    (int)vp->format);
      }
}

static void real_signal_value(struct t_vpi_value*vp, double rval)
{
      static const size_t RBUF_SIZE = 64 + 1;
      char*rbuf = static_cast<char *>(need_result_buf(RBUF_SIZE, RBUF_VAL));

      switch (vp->format) {
	  case vpiObjTypeVal:
	    vp->format = vpiRealVal;
	    // fallthrough
	  case vpiRealVal:
	    vp->value.real = rval;
	    break;

	  case vpiIntVal:
	      /* NaN or +/- infinity are translated as 0. */
	    if (rval != rval || (rval && (rval == 0.5*rval))) {
		  rval = 0.0;
	    } else {
		  rval = std::round(rval);
	    }
	    vp->value.integer = (PLI_INT32)rval;
	    break;

	  case vpiDecStrVal:
	    if (std::isnan(rval))
		  snprintf(rbuf, RBUF_SIZE, "%s", "nan");
	    else
		  snprintf(rbuf, RBUF_SIZE, "%0.0f", std::round(rval));
	    vp->value.str = rbuf;
	    break;

	  case vpiHexStrVal:
	    snprintf(rbuf, RBUF_SIZE, "%" PRIx64, vlg_round_to_u64(rval));
	    vp->value.str = rbuf;
	    break;

	  case vpiBinStrVal: {
		uint64_t val = vlg_round_to_u64(rval);
		unsigned len = 0;

		while (val > 0) {
		      len += 1;
		      val /= 2;
		}

		val = vlg_round_to_u64(rval);
		for (unsigned idx = 0 ;  idx < len ;  idx += 1) {
		      rbuf[len-idx-1] = (val & 1)? '1' : '0';
		      val /= 2;
		}

		rbuf[len] = 0;
		if (len == 0) {
		      rbuf[0] = '0';
		      rbuf[1] = 0;
		}
		vp->value.str = rbuf;
		break;
	  }

	  case vpiSuppressVal:
	    break;

	  default:
	    fprintf(stderr, "vpi_callback: value "
		    "format %d not supported (fun_signal_real)\n",
		    (int)vp->format);
      }
}

void vvp_fun_signal_real_aa::get_signal_value(struct t_vpi_value*vp)
{
      real_signal_value(vp, real_value());
}

void vvp_wire_real::get_signal_value(struct t_vpi_value*vp)
{
      real_signal_value(vp, real_value());
}

void vvp_fun_signal_string_aa::get_signal_value(struct t_vpi_value*)
{
      assert(0);
}
#if 0
void vvp_wire_string::get_signal_value(struct t_vpi_value*vp)
{
      assert(0);
}
#endif
void vvp_wire_vec4::get_value(struct t_vpi_value*val)
{
      get_signal_value(val);
}

void vvp_wire_vec8::get_value(struct t_vpi_value*val)
{
      get_signal_value(val);
}

void vvp_wire_real::get_value(struct t_vpi_value*val)
{
      get_signal_value(val);
}
#if 0
void vvp_wire_string::get_value(struct t_vpi_value*val)
{
      assert(0);
}
#endif

/* Call only on the simulator thread or while its coroutine mutex is held.
 * Function and user-data identity are compared with caller-supplied identities;
 * mismatches are observable and must not be admitted as complete coverage. */
/* The earlier API serialized unspecified fields. Fail closed if an old bridge
 * accidentally loads this runtime; only the versioned family API is supported. */
extern "C" int robotron_vvp_sync_inventory(FILE*, PLI_BYTE8*, robotron_callback_fn)
{
    return -1;
}

extern "C" int robotron_vvp_sync_family_inventory(FILE* stream, PLI_BYTE8* user,
                                                 robotron_callback_fn expected)
{
    if (!stream) return -1;
    if (fprintf(stream, "VF_BEGIN 1 %llu %d %llu\n",
                (unsigned long long)schedule_simtime(), (int)vpi_mode_flag,
                (unsigned long long)robotron_sync_live.size()) < 0) return -1;
    for (const auto& entry : robotron_sync_live) {
        const sync_callback* cb = entry.second;
        const s_cb_data& d = cb->cb_data;
        auto original = robotron_sync_functions.find(cb);
        if (original == robotron_sync_functions.end()) return -1;
        robotron_callback_fn registered = original->second;
        bool known = expected && registered == expected;
        unsigned high = 0, low = 0;
        double real = 0;
        if (cb->cb_time.type == vpiSimTime) {
            high = cb->cb_time.high; low = cb->cb_time.low;
        } else if (cb->cb_time.type == vpiScaledRealTime) real = cb->cb_time.real;
        else if (cb->cb_time.type != vpiSuppressTime) return -1;
        /* index is never read: it is not a general synchronization payload.
         * Only the explicitly supplied function's contract permits reading
         * user_data, obj and value. Other families stay visibly uncovered. */
        if (fprintf(stream,
            "VF_CB %llu %d %d %d %d %d %d %d %d %d %d %d %d %d %u %u %a\n",
            entry.first, cb == robotron_sync_executing,
            cb->cb_sync ? (int)cb->cb_sync->sync_flag : -1,
            d.reason, d.cb_rtn != 0, !d.cb_rtn || d.cb_rtn == registered, known,
            known ? (int)(d.user_data == user) : -1,
            known ? (int)(d.obj == 0) : -1, known ? (int)(d.value == 0) : -1,
            cb->next == 0, cb->cb_sync && cb->cb_sync->handle == cb,
            d.time == &cb->cb_time, cb->cb_time.type, high, low, real) < 0) return -1;
        Dl_info info = {};
        if (registered && dladdr(reinterpret_cast<void*>(registered), &info) && info.dli_fbase && info.dli_fname) {
            if (fprintf(stream, "VF_CODE %llu ", entry.first) < 0) return -1;
            for (const unsigned char* p = reinterpret_cast<const unsigned char*>(info.dli_fname); *p; ++p)
                if (fprintf(stream, "%02x", *p) < 0) return -1;
            uintptr_t offset = reinterpret_cast<uintptr_t>(registered) - reinterpret_cast<uintptr_t>(info.dli_fbase);
            if (fprintf(stream, " %llx\n", (unsigned long long)offset) < 0) return -1;
        } else if (fprintf(stream, "VF_CODE %llu - -\n", entry.first) < 0) return -1;
    }
    return fprintf(stream, "VF_END\n") < 0 || ferror(stream) ? -1 : 0;
}

/* A queued callback's synchronization mode affects execution semantics. Toggle
 * twice before resuming the scheduler; never mutate the executing callback. */
extern "C" int robotron_vvp_sync_toggle_queued_mode()
{
    for (const auto& entry : robotron_sync_live) {
        sync_callback* cb = entry.second;
        if (cb != robotron_sync_executing && cb->cb_sync && cb->cb_data.cb_rtn) {
            cb->cb_sync->sync_flag = !cb->cb_sync->sync_flag;
            return 1;
        }
    }
    return 0;
}

/* Compare opaque handles against live typed objects; never dereference a
 * supplied handle. Called only under simulator-thread/mutex ownership. */
static sync_callback* robotron_sync_from_handle(const void* handle)
{
    if (!handle) return 0;
    for (const auto& entry : robotron_sync_live)
        if (static_cast<const __vpiHandle*>(entry.second) == handle) return entry.second;
    return 0;
}
extern "C" unsigned long long robotron_vvp_sync_payload_identity(
    const void* handle, robotron_callback_fn function, PLI_BYTE8* user)
{
    sync_callback* cb = robotron_sync_from_handle(handle);
    if (!cb || !function) return 0;
    auto original = robotron_sync_functions.find(cb);
    if (original == robotron_sync_functions.end() || original->second != function ||
        cb->cb_data.cb_rtn != function || cb->cb_data.user_data != user) return 0;
    for (const auto& entry : robotron_sync_live)
        if (entry.second == cb) return entry.first;
    return 0;
}
/* Deliberate association fault: restore before executing either callback. */
extern "C" int robotron_vvp_sync_swap_payloads(
    const void* left, const void* right, robotron_callback_fn function)
{
    sync_callback* a = robotron_sync_from_handle(left);
    sync_callback* b = robotron_sync_from_handle(right);
    if (!a || !b || a == b || !function || a == robotron_sync_executing || b == robotron_sync_executing) return -1;
    auto af = robotron_sync_functions.find(a), bf = robotron_sync_functions.find(b);
    if (af == robotron_sync_functions.end() || bf == robotron_sync_functions.end() ||
        af->second != function || bf->second != function ||
        a->cb_data.cb_rtn != function || b->cb_data.cb_rtn != function ||
        !a->cb_data.user_data || !b->cb_data.user_data || a->cb_data.user_data == b->cb_data.user_data) return -1;
    const PLI_BYTE8* saved = a->cb_data.user_data;
    a->cb_data.user_data = b->cb_data.user_data;
    b->cb_data.user_data = saved;
    return 1;
}

/* Reversible association fault for a board with one pending display callback.
 * Caller must restore before handing scheduler ownership back to HDL. */
extern "C" int robotron_vvp_sync_toggle_payload_null(
    const void* handle, robotron_callback_fn function, PLI_BYTE8* expected_user)
{
    sync_callback* cb = robotron_sync_from_handle(handle);
    if (!cb || !function || !expected_user || cb == robotron_sync_executing) return -1;
    auto original = robotron_sync_functions.find(cb);
    if (original == robotron_sync_functions.end() || original->second != function ||
        cb->cb_data.cb_rtn != function) return -1;
    if (cb->cb_data.user_data == expected_user) cb->cb_data.user_data = 0;
    else if (!cb->cb_data.user_data) cb->cb_data.user_data = expected_user;
    else return -1;
    return 1;
}

/* Relate the executing generic event's opaque object to its live sync wrapper.
 * The supplied pointer is compared, never unpacked or dereferenced. */
extern "C" unsigned long long robotron_vvp_sync_executing_wrapper(const void* object)
{
    if (!object) return 0;
    for (const auto& entry : robotron_sync_live) {
        const sync_callback* cb = entry.second;
        if (cb != robotron_sync_executing || !cb->cb_sync || cb->cb_sync->handle != cb) continue;
        if (static_cast<const vvp_gen_event_s*>(cb->cb_sync) == object) return entry.first;
    }
    return 0;
}

/* Startup-only identity contract. Never dereference an unregistered handle or
 * list link. Suppressed time words and unrelated optional payloads are unread.
 * Invoke on the simulator thread or while its coroutine is paused. */
extern "C" unsigned long long robotron_vvp_start_identity(
    const void* handle, PLI_INT32 (*function)(p_cb_data), PLI_BYTE8* user)
{
    auto wanted = robotron_start_live.find(static_cast<const simulator_callback*>(handle));
    if (wanted == robotron_start_live.end() || !function || !user ||
        wanted->second.function != function) return 0;
    const simulator_callback* cb = wanted->first;
    if (cb->cb_data.reason != cbStartOfSimulation || cb->cb_data.cb_rtn != function ||
        cb->cb_data.user_data != user || cb->cb_data.time != &cb->cb_time ||
        cb->cb_time.type != vpiSuppressTime) return 0;
    std::set<const __vpiCallback*> seen;
    const __vpiCallback* node = StartOfSimulation;
    bool pending = false;
    while (node) {
        /* Compare base identities before accessing derived storage. */
        const simulator_callback* registered = 0;
        for (const auto& item : robotron_start_live)
            if (static_cast<const __vpiCallback*>(item.first) == node) registered = item.first;
        if (!registered || !seen.insert(node).second || registered == robotron_start_active) return 0;
        if (registered == cb) pending = true;
        node = registered->next;
    }
    bool active = cb == robotron_start_active;
    if (active && cb->next != robotron_start_active_next) return 0;
    return pending != active ? wanted->second.id : 0;
}

/* Restored negative controls only. No scheduler execution between the pair. */
extern "C" int robotron_vvp_start_toggle(
    const void* handle, PLI_INT32 (*function)(p_cb_data), PLI_BYTE8* user, int field)
{
    static simulator_callback* saved = 0;
    static int saved_field = -1;
    static const PLI_BYTE8* saved_user;
    static PLI_INT32 (*saved_function)(p_cb_data);
    static p_vpi_time saved_time;
    static __vpiCallback* saved_next;
    if (saved) {
        if (saved != handle || saved_field != field || !robotron_start_live.count(saved)) return -1;
        saved->cb_data.user_data = saved_user;
        saved->cb_data.cb_rtn = saved_function;
        saved->cb_data.time = saved_time;
        saved->next = saved_next;
        saved = 0; saved_field = -1;
        return 1;
    }
    if (field < 0 || field > 3 || !robotron_vvp_start_identity(handle,function,user)) return -1;
    saved = const_cast<simulator_callback*>(static_cast<const simulator_callback*>(handle));
    saved_field = field;
    saved_user = saved->cb_data.user_data;
    saved_function = saved->cb_data.cb_rtn;
    saved_time = saved->cb_data.time;
    saved_next = saved->next;
    switch (field) {
        case 0: saved->cb_data.user_data = 0; break;
        case 1: saved->cb_data.cb_rtn = 0; break;
        case 2: saved->cb_data.time = reinterpret_cast<p_vpi_time>(1); break;
        case 3: saved->next = reinterpret_cast<__vpiCallback*>(1); break;
    }
    return 1;
}

int vvp_vpi_callback::robotron_callback_heads(FILE* out) const
{
    return fprintf(out,"VWF_CALLBACKS %p %p\n",(void*)vpi_callbacks_,(void*)array_words_)<0?-1:0;
}

/* Complete list contents at a quiescent value-callback boundary. Active list
 * traversal has native stack cursors not covered here and is refused. */
struct robotron_callback_lists {
    static int inventory(FILE* out) {
        if(!out || robotron_callback_dispatch_depth)return -1;
        std::map<unsigned long long,vvp_vpi_callback*> owners;
        std::set<const value_callback*> callbacks;
        std::set<const __vpi_array_word*> words;
        for(auto item:robotron_callback_owners()) {
            auto owner=item.first;
            if(typeid(*owner)!=typeid(vvp_wire_vec4) && typeid(*owner)!=typeid(vvp_wire_vec8))return -1;
            owners[item.second]=owner;
            const void* cursor=owner->vpi_callbacks_;
            while(cursor) {
                auto found=robotron_value_live.find(cursor);
                if(found==robotron_value_live.end())return -1;
                auto cb=found->second.callback;
                if(found->second.owner!=owner || !found->second.list_admitted || typeid(*cb)!=typeid(value_callback) || !callbacks.insert(cb).second)return -1;
                if(cb->cb_data.reason!=cbValueChange || cb->cb_data.time!=&cb->cb_time || cb->cb_data.value!=&cb->cb_value || cb->cb_time.type!=vpiSuppressTime || cb->cb_value.format!=vpiVectorVal)return -1;
                cursor=cb->next;
            }
            auto word=owner->array_words_;
            while(word) {
                auto found=robotron_callback_words().find(word);
                if(found==robotron_callback_words().end() || found->second.owner!=owner || !words.insert(word).second)return -1;
                word=word->next;
            }
        }
        if(callbacks.size()!=robotron_value_live.size() || words.size()!=robotron_callback_words().size())return -1;
        if(fprintf(out,"VCL_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
        for(auto item:owners) {
            auto owner=item.second;unsigned count=0,word_count=0;
            for(auto cb=owner->vpi_callbacks_;cb;cb=static_cast<value_callback*>(cb->next))++count;
            for(auto word=owner->array_words_;word;word=word->next)++word_count;
            if(fprintf(out,"VCL_OWNER %llu %p %s %p %p %u %u\n",item.first,(void*)owner,typeid(*owner).name(),(void*)owner->vpi_callbacks_,(void*)owner->array_words_,count,word_count)<0)return -1;
            for(auto cb=owner->vpi_callbacks_;cb;cb=static_cast<value_callback*>(cb->next)) {
                const auto& entry=robotron_value_live.at(cb);
                if(fprintf(out,"VCL_CALLBACK %llu %p %p %d %p %p %p %p %p %d %d\n",(unsigned long long)entry.id,(void*)cb,(void*)cb->next,cb->cb_data.reason,(void*)cb->cb_data.cb_rtn,(void*)cb->cb_data.obj,(void*)cb->cb_data.user_data,(void*)cb->cb_data.time,(void*)cb->cb_data.value,cb->cb_time.type,cb->cb_value.format)<0)return -1;
            }
            for(auto word=owner->array_words_;word;word=word->next) {
                const auto& entry=robotron_callback_words().at(word);
                if(fprintf(out,"VCL_WORD %llu %p %p %p %lu\n",entry.id,(void*)word,(void*)word->next,(void*)word->array,word->word)<0)return -1;
            }
        }
        return fprintf(out,"VCL_END %zu %zu %zu\n",owners.size(),callbacks.size(),words.size())<0 || ferror(out)?-1:0;
    }
};
extern "C" int robotron_vvp_callback_list_inventory(FILE* out)
{return robotron_callback_lists::inventory(out);}

/* Test actual association fields without following corrupted referents.
 * Every paired fault must restore before any native value dispatch. */
extern "C" int robotron_vvp_callback_word_toggle(unsigned long long id,int field)
{
    static __vpi_array_word* saved=0;static unsigned long long saved_id;
    static int saved_field;static __vpi_array_word* saved_next;
    static __vpiArray* saved_array;static unsigned long saved_word;
    if(robotron_callback_dispatch_depth || field<0 || field>2)return -1;
    __vpi_array_word* target=0;
    for(auto item:robotron_callback_words())if(item.second.id==id)target=item.first;
    if(saved) {
        if(target!=saved || id!=saved_id || field!=saved_field)return -1;
        saved->next=saved_next;saved->array=saved_array;saved->word=saved_word;saved=0;return 1;
    }
    if(!target)return 0;
    saved=target;saved_id=id;saved_field=field;saved_next=target->next;saved_array=target->array;saved_word=target->word;
    if(field==0)target->word^=1;
    else if(field==1)target->array=reinterpret_cast<__vpiArray*>(uintptr_t(1));
    else target->next=reinterpret_cast<__vpi_array_word*>(uintptr_t(1));
    return 1;
}

#include <sstream>
#include <string>

// Scan all fields; encode each callback owner independently against an immutable reference.
static std::map<unsigned long long,std::string> robotron_callback_delta_reference_rows;
static bool robotron_callback_delta_reference_ready;
static int robotron_callback_delta_rows(std::map<unsigned long long,std::string>& rows)
{
    char* data=0;size_t size=0;FILE* stream=open_memstream(&data,&size);
    if(!stream)return -1;
    int result=robotron_vvp_callback_list_inventory(stream);
    if(fclose(stream))result=-1;
    if(result){free(data);return -1;}
    std::string text(data,size);free(data);std::istringstream input(text);std::string line;
    if(!std::getline(input,line) || line.compare(0,10,"VCL_BEGIN "))return -1;
    unsigned long long id=0;
    while(std::getline(input,line)){
        if(line.compare(0,10,"VCL_OWNER ")==0){
            std::istringstream row(line);std::string marker;row>>marker>>id;
            if(!id || rows.count(id))return -1;
            rows[id]=line+"\n";
        }else if((line.compare(0,13,"VCL_CALLBACK ")==0 || line.compare(0,9,"VCL_WORD ")==0)){
            if(!id)return -1;rows[id]+=line+"\n";
        }else if(line.compare(0,8,"VCL_END ")==0){
            return std::getline(input,line)?-1:0;
        }else return -1;
    }
    return -1;
}
static int robotron_callback_delta_row(FILE* out,unsigned long long id,const std::string& row,const std::string& reference)
{
    size_t prefix=0,suffix=0;
    while(prefix<row.size() && prefix<reference.size() && row[prefix]==reference[prefix])prefix++;
    while(suffix<row.size()-prefix && suffix<reference.size()-prefix && row[row.size()-1-suffix]==reference[reference.size()-1-suffix])suffix++;
    if(fprintf(out,"VLD_ROW %llu %zu %zu ",id,prefix,suffix)<0)return -1;
    static const char digits[]="0123456789abcdef";
    if(prefix+suffix==row.size()){if(fputc('-',out)==EOF)return -1;}
    else for(size_t i=prefix;i<row.size()-suffix;i++){
        unsigned char c=row[i];if(fputc(digits[c>>4],out)==EOF || fputc(digits[c&15],out)==EOF)return -1;
    }
    return fputc('\n',out)==EOF?-1:0;
}
extern "C" int robotron_vvp_callback_list_reference(FILE* out)
{
    if(!out || robotron_callback_delta_reference_ready)return -1;
    std::map<unsigned long long,std::string> rows;
    if(robotron_callback_delta_rows(rows))return -1;
    if(fprintf(out,"VLD_BEGIN R %llu %zu %zu %zu\n",(unsigned long long)schedule_simtime(),rows.size(),rows.size(),size_t(0))<0)return -1;
    for(auto row:rows)if(robotron_callback_delta_row(out,row.first,row.second,""))return -1;
    if(fprintf(out,"VLD_END %zu 0\n",rows.size())<0 || ferror(out))return -1;
    robotron_callback_delta_reference_rows=rows;robotron_callback_delta_reference_ready=true;return 0;
}
extern "C" int robotron_vvp_callback_list_delta_inventory(FILE* out)
{
    if(!out || !robotron_callback_delta_reference_ready)return -1;
    std::map<unsigned long long,std::string> rows;
    if(robotron_callback_delta_rows(rows))return -1;
    size_t removed=0;for(auto row:robotron_callback_delta_reference_rows)if(!rows.count(row.first))removed++;
    size_t changed=0;
    for(auto row:rows){auto old=robotron_callback_delta_reference_rows.find(row.first);if(old==robotron_callback_delta_reference_rows.end() || old->second!=row.second)changed++;}
    if(fprintf(out,"VLD_BEGIN D %llu %zu %zu %zu\n",(unsigned long long)schedule_simtime(),rows.size(),changed,removed)<0)return -1;
    for(auto row:rows){
        auto old=robotron_callback_delta_reference_rows.find(row.first);
        if(old==robotron_callback_delta_reference_rows.end() || old->second!=row.second)
            if(robotron_callback_delta_row(out,row.first,row.second,old==robotron_callback_delta_reference_rows.end()?"":old->second))return -1;
    }
    for(auto row:robotron_callback_delta_reference_rows)if(!rows.count(row.first))if(fprintf(out,"VLD_DROP %llu\n",row.first)<0)return -1;
    return fprintf(out,"VLD_END %zu %zu\n",changed,removed)<0 || ferror(out)?-1:0;
}

extern "C" int robotron_vvp_signal_handle_inventory(FILE*);
extern "C" unsigned long long robotron_vvp_signal_handle_node(vpiHandle,void**);
extern "C" unsigned long long robotron_vvp_net_handle_id(const void*);
static int robotron_link_preflight(int(*api)(FILE*))
{
    char*text=0;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return -1;
    int result=api(f);if(fclose(f))result=-1;free(text);return result;
}
extern "C" int robotron_vvp_callback_signal_inventory(FILE*out)
{
    if(!out || robotron_link_preflight(robotron_vvp_callback_list_inventory) ||
       robotron_link_preflight(robotron_vvp_signal_handle_inventory))return -1;
    struct row_t {
        unsigned long long callback_id,handle_id,owner_id,node_id;
        value_callback*callback;vpiHandle handle;vvp_vpi_callback*owner;
        vvp_net_fil_t*filter;vvp_net_t*node;
    };
    std::map<unsigned long long,row_t> rows;
    for(auto item:robotron_value_live){
        auto entry=item.second;auto owner=robotron_callback_owners().find(entry.owner);
        if(owner==robotron_callback_owners().end())return -1;
        // List preflight established the exact registered owner class.
        auto filter=dynamic_cast<vvp_net_fil_t*>(entry.owner);
        void*address=0;auto handle=entry.callback->cb_data.obj;
        auto id=robotron_vvp_signal_handle_node(handle,&address);
        auto node=static_cast<vvp_net_t*>(address);auto node_id=robotron_vvp_net_handle_id(node);
        // Never cast/dereference an unregistered filter pointer read from a node.
        if(!id || !node_id || !filter || node->fil!=filter)return -1;
        rows[entry.id]={entry.id,id,owner->second,node_id,entry.callback,handle,entry.owner,filter,node};
    }
    if(fprintf(out,"VSL_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
    for(auto item:rows){auto&r=item.second;
        if(fprintf(out,"VSL_LINK %llu %p %llu %p %llu %p %p %llu %p\n",
            r.callback_id,(void*)r.callback,r.handle_id,(void*)r.handle,r.owner_id,
            (void*)r.owner,(void*)r.filter,r.node_id,(void*)r.node)<0)return -1;
    }
    return fprintf(out,"VSL_END %zu\n",rows.size())<0 || ferror(out)?-1:0;
}

extern "C" int robotron_vvp_signal_handle_reference_inventory(FILE*);
extern "C" int robotron_vvp_callback_signal_reference_inventory(FILE*out)
{
    if(!out || robotron_link_preflight(robotron_vvp_callback_list_inventory) ||
       robotron_link_preflight(robotron_vvp_signal_handle_reference_inventory))return -1;
    struct row_t {
        unsigned long long callback_id,handle_id,owner_id,node_id;
        value_callback*callback;vpiHandle handle;vvp_vpi_callback*owner;
        vvp_net_fil_t*filter;vvp_net_t*node;
    };
    std::map<unsigned long long,row_t> rows;
    for(auto item:robotron_value_live){
        auto entry=item.second;auto owner=robotron_callback_owners().find(entry.owner);
        if(owner==robotron_callback_owners().end())return -1;
        // List preflight established the exact registered owner class.
        auto filter=dynamic_cast<vvp_net_fil_t*>(entry.owner);
        void*address=0;auto handle=entry.callback->cb_data.obj;
        auto id=robotron_vvp_signal_handle_node(handle,&address);
        auto node=static_cast<vvp_net_t*>(address);auto node_id=robotron_vvp_net_handle_id(node);
        // Never cast/dereference an unregistered filter pointer read from a node.
        if(!id || !node_id || !filter || node->fil!=filter)return -1;
        rows[entry.id]={entry.id,id,owner->second,node_id,entry.callback,handle,entry.owner,filter,node};
    }
    if(fprintf(out,"VSL_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
    for(auto item:rows){auto&r=item.second;
        if(fprintf(out,"VSL_LINK %llu %p %llu %p %llu %p %p %llu %p\n",
            r.callback_id,(void*)r.callback,r.handle_id,(void*)r.handle,r.owner_id,
            (void*)r.owner,(void*)r.filter,r.node_id,(void*)r.node)<0)return -1;
    }
    return fprintf(out,"VSL_END %zu\n",rows.size())<0 || ferror(out)?-1:0;
}
