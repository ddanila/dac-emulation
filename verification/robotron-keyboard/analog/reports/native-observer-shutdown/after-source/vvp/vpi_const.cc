extern "C" int robotron_vvp_observation_active();
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

# include  "vpi_priv.h"
# include  "compile.h"
# include  "config.h"
#ifdef CHECK_WITH_VALGRIND
# include  "vvp_cleanup.h"
#endif
# include  <cstdio>
# include  <cstdlib>
# include  <cstring>
# include  <climits>
# include  <cassert>
# include  "ivl_alloc.h"

static void robotron_parameter_register(vpiHandle);
static void robotron_parameter_unregister(vpiHandle);
static unsigned robotron_parameter_unsupported=0;
// Diagnostic factory selection; normal construction remains the exact native class.
static bool robotron_parameter_subclass(const char*kind){
    const char*mode=getenv("ROBOTRON_PARAMETER_CLASS");return mode&&!strcmp(mode,kind);
}
extern "C" unsigned robotron_vvp_parameter_unsupported_count(){return robotron_parameter_unsupported;}


class __vpiStringConst : public __vpiHandle {
      friend struct robotron_parameter_access;
    public:
      explicit __vpiStringConst(char*val);
      ~__vpiStringConst() override;
      int get_type_code(void) const override;
      int vpi_get(int code) override;
      void vpi_get_value(p_vpi_value val) override;

    private:
      void process_string_();
    private:
      char*value_;
      size_t value_len_;
};

inline __vpiStringConst::__vpiStringConst(char*v)
: value_(v)
{
      process_string_();
}

/*
 * Strings are described at the level of the vvp source as a string
 * with literal characters or octal escapes. No other escapes are
 * included, they are processed already by the compiler that generated
 * the vvp source.
 */
void __vpiStringConst::process_string_(void)
{
      char*chr = value_;
      char*dp = value_;

      while (*chr) {
	    char next_char = *chr;

	      /* Process octal escapes that I might find. */
	    if (*chr == '\\') {
		  for (int idx = 1 ;  idx <= 3 ;  idx += 1) {
			assert(chr[idx] != 0);
			assert(chr[idx] < '8');
			assert(chr[idx] >= '0');
			next_char = next_char*8 + chr[idx] - '0';
		  }
		  chr += 3;
	    }
	    *dp++ = next_char;
	    chr += 1;
      }
      *dp = 0;
      value_len_ = dp - value_;
}

__vpiStringConst::~__vpiStringConst()
{
      delete[] value_;
}

int __vpiStringConst::get_type_code(void) const
{ return vpiConstant; }

int __vpiStringConst::vpi_get(int code)
{
      switch (code) {
          case vpiSize:
	    return value_len_ * 8;

          case vpiSigned:
	      return 0;

	  case vpiConstType:
	      return vpiStringConst;

          case vpiAutomatic:
	      return 0;

#if defined(CHECK_WITH_VALGRIND) || defined(BR916_STOPGAP_FIX)
          case _vpiFromThr:
	      return _vpiNoThr;
#endif

	  default:
	      fprintf(stderr, "vvp error: get %d not supported "
		      "by vpiStringConst\n", code);
	      assert(0);
	      return 0;
      }
}

void __vpiStringConst::vpi_get_value(p_vpi_value vp)
{
      unsigned uint_value;
      p_vpi_vecval vecp;
      unsigned size = value_len_;
      char*rbuf = 0;
      char*cp;

      switch (vp->format) {
	  case vpiObjTypeVal:
	      /* String parameters by default have vpiStringVal values. */
	    vp->format = vpiStringVal;
	    // fallthrough
	  case vpiStringVal:
	    cp = value_;
	    rbuf = static_cast<char *>(need_result_buf(size + 1, RBUF_VAL));
	    vp->value.str = rbuf;

	    for (unsigned int i = 0; i < size; i++) {
		  // Ignore leading null-bytes and replace other null-bytes with space.
		  // The LRM is not entirely clear on how null bytes should be handled.
		  // This is the implementation chosen for iverilog.
		  if (*cp)
			*rbuf++ = *cp;
		  else if (rbuf != vp->value.str)
			*rbuf++ = ' ';

		  cp++;
	    }
	    *rbuf = '\0';
	    break;

          case vpiDecStrVal:
	    // Take the (up to 4) characters of the text, convert the characters
	    // to a numerical value, and convert that value to a decimal string.
	    // For example, the string "A" is ASCII 65, so the resulting string
	    // will be "65". and the string "AB" is 65*256 + 66 == 16706, so
	    // the resulting string is "16706". The "size" is the number of
	    // characters of input text to put to work.
	    if (size > 4){
		  // We only support standard integers. Ignore other bytes...
		  size = 4;
		  fprintf(stderr, "Warning (vpi_const.cc): %%d on constant strings only looks "
			  "at first 4 bytes!\n");
	    }
	    static const size_t RBUF_USE_SIZE = 12;
	    rbuf = static_cast<char *>(need_result_buf(RBUF_USE_SIZE, RBUF_VAL));
	    uint_value = 0;
	    for(unsigned i=0; i<size; i += 1){
		  uint_value <<=8;
		  uint_value += (unsigned char)(value_[i]);
	    }
	    snprintf(rbuf, RBUF_USE_SIZE, "%u", uint_value);
	    vp->value.str = rbuf;
	    break;

          case vpiBinStrVal:
	      rbuf = static_cast<char *>(need_result_buf(8 * size + 1, RBUF_VAL));
	      cp = rbuf;
	      for(unsigned i=0; i<size; i += 1){
		  for(int bit=7; bit>=0; bit -= 1){
		      *cp++ = "01"[ (value_[i]>>bit)&1 ];
		  }
	      }
	      *cp = 0;
	      vp->value.str = rbuf;
	      break;

          case vpiHexStrVal:
	      rbuf = static_cast<char *>(need_result_buf(2 * size + 1, RBUF_VAL));
	      cp = rbuf;
	      for(unsigned i=0; i<size; i += 1){
		  for(int nibble=1; nibble>=0; nibble -= 1){
		      *cp++ = "0123456789abcdef"[ (value_[i]>>(nibble*4))&15 ];
		  }
	      }
	      *cp = 0;
	      vp->value.str = rbuf;
	      break;

          case vpiOctStrVal:
	      fprintf(stderr, "ERROR (vpi_const.cc): %%o display of constant strings not yet implemented\n");
	      assert(0);
	      break;

          case vpiIntVal:
	      vp->value.integer = 0;
	      for(unsigned i=0; i<size; i += 1){
		  for(int bit=7; bit>=0; bit -= 1){
		      vp->value.integer <<= 1;
		      vp->value.integer += (value_[i]>>bit)&1;
		  }
	      }
	      break;

          case vpiVectorVal:
              vp->value.vector = static_cast<p_vpi_vecval>
                                 (need_result_buf((size+3)/4*
                                                   sizeof(s_vpi_vecval),
                                                  RBUF_VAL));
              uint_value = 0;
              vecp = vp->value.vector;
              vecp->aval = vecp->bval = 0;
	      for(unsigned i=0; i<size; i += 1){
		  vecp->aval |= value_[i] << uint_value*8;
		  uint_value += 1;
		  if (uint_value > 3) {
		      uint_value = 0;
		      vecp += 1;
		      vecp->aval = vecp->bval = 0;
		  }
	      }
	      break;


	  default:
	    fprintf(stderr, "ERROR (vpi_const.cc): vp->format: %d\n",
	            (int)vp->format);
	    assert(0);

	    vp->format = vpiSuppressVal;
	    break;
      }
}


struct __vpiStringConstTEMP : public __vpiStringConst {
      explicit inline __vpiStringConstTEMP(char*v) : __vpiStringConst(v) { }
      free_object_fun_t free_object_fun(void) override;
};

static int free_temp_string(vpiHandle obj)
{
      struct __vpiStringConstTEMP*rfp = dynamic_cast<__vpiStringConstTEMP*>(obj);
      delete rfp;
      return 1;
}

__vpiHandle::free_object_fun_t __vpiStringConstTEMP::free_object_fun(void)
{ return &free_temp_string; }

vpiHandle vpip_make_string_const(char*text, bool persistent_flag)
{
      __vpiStringConst*obj;

      obj = persistent_flag? new __vpiStringConst(text) : new __vpiStringConstTEMP(text);

      return obj;
}


class __vpiStringParam  : public __vpiStringConst {
      friend struct robotron_parameter_access;
    public:
      __vpiStringParam(__vpiScope* scope, char*txt, const char*name,
                       bool local_flag, long file_idx, long lineno);
      ~__vpiStringParam() override;
      int get_type_code(void) const override;
      int vpi_get(int code) override;
      char*vpi_get_str(int code) override;
      vpiHandle vpi_handle(int code) override;

    private:
      __vpiScope* scope_;
      const char*basename_;
      bool       local_flag_;
      unsigned   file_idx_;
      unsigned   lineno_;
};

inline __vpiStringParam::__vpiStringParam(__vpiScope* scope, char*txt, const char*nam,
                                          bool local_flag, long file_idx, long lineno)
: __vpiStringConst(txt)
{
      scope_ = scope;
      basename_ = nam;
      local_flag_ = local_flag;
      assert(file_idx >= 0 && file_idx <= INT_MAX);
      file_idx_ = (unsigned) file_idx;
      assert(lineno >= 0 && lineno <= INT_MAX);
      lineno_ = (unsigned) lineno;
}

__vpiStringParam::~__vpiStringParam()
{
      if(getenv("ROBOTRON_TEARDOWN_TRACE")) fprintf(stdout,"TEARDOWN_PARAMETER String %p\n",(void*)this);
      robotron_parameter_unregister(this);
      delete[]basename_;
}

int __vpiStringParam::get_type_code(void) const
{ return vpiParameter; }

int __vpiStringParam::vpi_get(int code)
{
    switch (code) {
       case vpiLineNo :
         return lineno_;

       case vpiLocalParam :
         return local_flag_;

       default :
         return __vpiStringConst::vpi_get(code);
    }
}


char*__vpiStringParam::vpi_get_str(int code)
{
      if (code == vpiFile) {
	    return simple_set_rbuf_str(file_names[file_idx_]);
      }

      return generic_get_str(code, scope_, basename_, NULL);
}


vpiHandle __vpiStringParam::vpi_handle(int code)
{
      switch (code) {
	  case vpiScope:
	    return scope_;

	  case vpiModule:
	    return vpip_module(scope_);

	  default:
	    return 0;
      }
}

struct robotron_string_param_extra : public __vpiStringParam {
    using __vpiStringParam::__vpiStringParam;
    unsigned hidden=0x7658;
};

vpiHandle vpip_make_string_param(const char*name, char*text,
                                 bool local_flag, long file_idx, long lineno)
{
      __vpiStringParam*obj = robotron_parameter_subclass("string")? new robotron_string_param_extra(vpip_peek_current_scope(), text, name,
                                                  local_flag, file_idx, lineno) : new __vpiStringParam(vpip_peek_current_scope(), text, name,
                                                  local_flag, file_idx, lineno);

      robotron_parameter_register(obj);
      return obj;
}



inline __vpiBinaryConst::__vpiBinaryConst()
: signed_flag(0), sized_flag(0)
{ }

int __vpiBinaryConst::get_type_code(void) const
{ return vpiConstant; }

int __vpiBinaryConst::vpi_get(int code)
{
      switch (code) {
	  case vpiConstType:
	    return vpiBinaryConst;

	  case vpiLineNo:
	    return 0;  // Not implemented for now!

	  case vpiSigned:
	    return signed_flag? 1 : 0;

	  case vpiSize:
	    return bits.size();

          case vpiAutomatic:
	    return 0;

#if defined(CHECK_WITH_VALGRIND) || defined(BR916_STOPGAP_FIX)
          case _vpiFromThr:
	      return _vpiNoThr;
#endif

	  default:
	    fprintf(stderr, "vvp error: get %d not supported "
		    "by vpiBinaryConst\n", code);
	    assert(0);
	    return 0;
      }
}


void __vpiBinaryConst::vpi_get_value(p_vpi_value val)
{
      switch (val->format) {

	  case vpiObjTypeVal:
	  case vpiBinStrVal:
	  case vpiDecStrVal:
	  case vpiOctStrVal:
	  case vpiHexStrVal:
          case vpiScalarVal:
	  case vpiIntVal:
	  case vpiVectorVal:
	  case vpiStringVal:
	  case vpiRealVal:
	    vpip_vec4_get_value(bits, bits.size(), signed_flag, val);
	    break;

	  default:
	    fprintf(stderr, "vvp error: format %d not supported "
		    "by vpiBinaryConst\n", (int)val->format);
	    val->format = vpiSuppressVal;
	    break;
      }
}

/*
 * Make a VPI constant from a vector string. The string is normally a
 * ASCII string, with each letter a 4-value bit. The first character
 * may be an 's' if the vector is signed.
 */
vpiHandle vpip_make_binary_const(unsigned wid, const char*bits)
{
      struct __vpiBinaryConst*obj = new __vpiBinaryConst;

      const char*bp = bits;
      if (*bp == 's') {
	    bp += 1;
	    obj->signed_flag = 1;
      }

      obj->bits = vector4_from_text(bp, wid);

      return obj;
}

vvp_vector4_t vector4_from_text(const char*bits, unsigned wid)
{
      vvp_vector4_t res (wid);

      for (unsigned idx = 0 ;  idx < wid ;  idx += 1) {
	    vvp_bit4_t val = BIT4_0;
	    switch (bits[wid-idx-1]) {
		case '0':
		  val = BIT4_0;
		  break;
		case '1':
		  val = BIT4_1;
		  break;
		case 'x':
		  val = BIT4_X;
		  break;
		case 'z':
		  val = BIT4_Z;
		  break;
	    }

	    res.set_bit(idx, val);
      }

      return res;
}

struct __vpiBinaryParam  : public __vpiBinaryConst {
      friend struct robotron_parameter_access;
      __vpiBinaryParam(__vpiScope*scope, const vvp_vector4_t&b, bool is_signed,
                       const char*name, bool local_flag, long file_idx, long lineno);
      ~__vpiBinaryParam() override;
      int get_type_code(void) const override;
      int vpi_get(int code) override;
      char*vpi_get_str(int code) override;
      vpiHandle vpi_handle(int code) override;

    private:
      __vpiScope*scope_;
      const char*basename_;
      bool     local_flag_;
      unsigned file_idx_;
      unsigned lineno_;
};

inline __vpiBinaryParam::__vpiBinaryParam(__vpiScope*scope, const vvp_vector4_t&b,
                                          bool is_signed, const char*nam,
                                          bool local_flag, long file_idx, long lineno)
{
      scope_ = scope;
      bits = b;
      signed_flag = is_signed ? 1 : 0;
      sized_flag = 0;
      basename_ = nam;
      local_flag_ = local_flag;
      assert(file_idx >= 0 && file_idx <= INT_MAX);
      file_idx_ = (unsigned) file_idx;
      assert(lineno >= 0 && lineno <= INT_MAX);
      lineno_ = (unsigned) lineno;
}

__vpiBinaryParam::~__vpiBinaryParam()
{
      if(getenv("ROBOTRON_TEARDOWN_TRACE")) fprintf(stdout,"TEARDOWN_PARAMETER Binary %p\n",(void*)this);
      robotron_parameter_unregister(this);
      delete[]basename_;
}

int __vpiBinaryParam::get_type_code(void) const
{ return vpiParameter; }

int __vpiBinaryParam::vpi_get(int code)
{
    switch (code) {
      case vpiLineNo :
        return lineno_;

      case vpiLocalParam :
        return local_flag_;

      default :
        return __vpiBinaryConst::vpi_get(code);
    }
}

char*__vpiBinaryParam::vpi_get_str(int code)
{
      if (code == vpiFile)
	    return simple_set_rbuf_str(file_names[file_idx_]);

      return generic_get_str(code, scope_, basename_, NULL);
}


vpiHandle __vpiBinaryParam::vpi_handle(int code)
{
      switch (code) {
	  case vpiScope:
	    return scope_;

	  case vpiModule:
	    return vpip_module(scope_);

	  default:
	    return 0;
      }
}


struct robotron_binary_param_extra : public __vpiBinaryParam {
    using __vpiBinaryParam::__vpiBinaryParam;
    unsigned hidden=0x7658;
};

vpiHandle vpip_make_binary_param(const char*name, const vvp_vector4_t&bits,
				 bool signed_flag, bool local_flag,
				 long file_idx, long lineno)
{
      struct __vpiBinaryParam*obj = robotron_parameter_subclass("binary")? new robotron_binary_param_extra(vpip_peek_current_scope(),
                                                         bits, signed_flag, name,
                                                         local_flag, file_idx, lineno) : new __vpiBinaryParam(vpip_peek_current_scope(),
                                                         bits, signed_flag, name,
                                                         local_flag, file_idx, lineno);

      robotron_parameter_register(obj);
      return obj;
}



__vpiDecConst::__vpiDecConst(int val)
{
      value = val;
}

__vpiDecConst::__vpiDecConst(const __vpiDecConst&that)
: __vpiHandle(), value(that.value)
{
}


int __vpiDecConst::get_type_code(void) const
{ return vpiConstant; }

int __vpiDecConst::vpi_get(int code)
{
      switch (code) {
	  case vpiConstType:
	    return vpiDecConst;

	  case vpiSigned:
	    return 1;

	  case vpiSize:
	    return 32;

          case vpiAutomatic:
	    return 0;

#if defined(CHECK_WITH_VALGRIND) || defined(BR916_STOPGAP_FIX)
          case _vpiFromThr:
	      return _vpiNoThr;
#endif

	  default:
	    fprintf(stderr, "vvp error: get %d not supported "
		    "by vpiDecConst\n", code);
	    assert(0);
	    return 0;
      }
}


void __vpiDecConst::vpi_get_value(p_vpi_value vp)
{
      static const size_t RBUF_USE_SIZE = 64 + 1;
      char*rbuf = static_cast<char *>(need_result_buf(RBUF_USE_SIZE, RBUF_VAL));
      char*cp = rbuf;

      switch (vp->format) {

	  case vpiObjTypeVal:
	  case vpiIntVal: {
		vp->value.integer = value;
		break;
	  }

          case vpiDecStrVal:
	      snprintf(rbuf, RBUF_USE_SIZE, "%d", value);
	      vp->value.str = rbuf;
	      break;

          case vpiBinStrVal:
	      for(int bit=31; bit>=0;bit--){
		  *cp++ = "01"[ (static_cast<unsigned>(value)>>bit)&1 ];
	      }
	      *cp = 0;

	      vp->value.str = rbuf;
	      break;

          case vpiHexStrVal:
	      snprintf(rbuf, RBUF_USE_SIZE, "%08x", value);
	      vp->value.str = rbuf;
	      break;

          case vpiOctStrVal:
	      snprintf(rbuf, RBUF_USE_SIZE, "%011x", value);
	      vp->value.str = rbuf;
	      break;

	  default:
	    fprintf(stderr, "vvp error (vpi_const.cc): format %d not supported "
		    "by vpiDecConst\n", (int)vp->format);
	    vp->format = vpiSuppressVal;
	    break;
      }
}


inline __vpiRealConst::__vpiRealConst(double val)
: value(val)
{ }

int __vpiRealConst::get_type_code(void) const
{ return vpiConstant; }

int __vpiRealConst::vpi_get(int code)
{
      switch (code) {
	  case vpiLineNo:
	    return 0;  // Not implemented for now!

	  case vpiSize:
	    return 1;

	  case vpiConstType:
	    return vpiRealConst;

	  case vpiSigned:
	    return 1;

          case vpiAutomatic:
	    return 0;

#if defined(CHECK_WITH_VALGRIND) || defined(BR916_STOPGAP_FIX)
          case _vpiFromThr:
	      return _vpiNoThr;
#endif

	  default:
	    fprintf(stderr, "vvp error: get %d not supported "
		    "by vpiRealConst\n", code);
	    assert(0);
	    return 0;
      }
}


void __vpiRealConst::vpi_get_value(p_vpi_value val)
{
      vpip_real_get_value(value, val);
}


vpiHandle vpip_make_real_const(double value)
{
      __vpiRealConst*obj = new __vpiRealConst(value);
      return obj;
}

struct __vpiRealParam  : public __vpiRealConst {
      friend struct robotron_parameter_access;
      __vpiRealParam(__vpiScope* scope, double val, const char*name,
                     bool local_flag, long file_idx, long lineno);
      ~__vpiRealParam() override;
      int get_type_code(void) const override;
      int vpi_get(int code) override;
      char*vpi_get_str(int code) override;
      vpiHandle vpi_handle(int code) override;

    private:
      __vpiScope* scope_;
      const char*basename_;
      bool local_flag_;
      unsigned file_idx_;
      unsigned lineno_;
};


inline __vpiRealParam::__vpiRealParam(__vpiScope* scope, double val, const char*name,
                                      bool local_flag, long file_idx, long lineno)
: __vpiRealConst(val)
{
      scope_ = scope;
      basename_ = name;
      local_flag_ = local_flag;
      assert(file_idx >= 0 && file_idx <= INT_MAX);
      file_idx_ = (unsigned) file_idx;
      assert(lineno >= 0 && lineno <= INT_MAX);
      lineno_ = (unsigned) lineno;
}

__vpiRealParam::~__vpiRealParam()
{
      if(getenv("ROBOTRON_TEARDOWN_TRACE")) fprintf(stdout,"TEARDOWN_PARAMETER Real %p\n",(void*)this);
      robotron_parameter_unregister(this);
      delete[]basename_;
}


int __vpiRealParam::get_type_code(void) const
{ return vpiParameter; }

int __vpiRealParam::vpi_get(int code)
{
    switch (code) {
      case vpiLineNo :
        return lineno_;

      case vpiLocalParam :
        return local_flag_;

      default :
           return __vpiRealConst::vpi_get(code);
    }
}

char* __vpiRealParam::vpi_get_str(int code)
{
      if (code == vpiFile)
            return simple_set_rbuf_str(file_names[file_idx_]);

      return generic_get_str(code, scope_, basename_, NULL);
}

vpiHandle __vpiRealParam::vpi_handle(int code)
{
      switch (code) {
          case vpiScope:
            return scope_;

	  case vpiModule:
	    return vpip_module(scope_);

          default:
            return 0;
      }
}


struct robotron_real_param_extra : public __vpiRealParam {
    using __vpiRealParam::__vpiRealParam;
    unsigned hidden=0x7658;
};

vpiHandle vpip_make_real_param(const char*name, double value,
                               bool local_flag, long file_idx, long lineno)
{
      struct __vpiRealParam*obj = robotron_parameter_subclass("real")? new robotron_real_param_extra(vpip_peek_current_scope(),
                                                     value, name, local_flag,
                                                     file_idx, lineno) : new __vpiRealParam(vpip_peek_current_scope(),
                                                     value, name, local_flag,
                                                     file_idx, lineno);
      robotron_parameter_register(obj);
      return obj;
}

/*
 * Make a VPI null constant
 */
inline __vpiNullConst::__vpiNullConst()
{ }

int __vpiNullConst::get_type_code(void) const
{ return vpiConstant; }

int __vpiNullConst::vpi_get(int code)
{
      switch (code) {
	  case vpiLineNo:
	    return 0;  // Not implemented for now!

	  case vpiSize:
	    return 32;

	  case vpiConstType:
	    return vpiNullConst;

	  case vpiSigned:
	    return 0;

          case vpiAutomatic:
	    return 0;

#if defined(CHECK_WITH_VALGRIND) || defined(BR916_STOPGAP_FIX)
          case _vpiFromThr:
	      return _vpiNoThr;
#endif

	  default:
	    fprintf(stderr, "vvp error: get %d not supported "
		    "by vpiNullConst\n", code);
	    assert(0);
	    return 0;
      }
}

void __vpiNullConst::vpi_get_value(p_vpi_value val)
{
      static const size_t RBUF_USE_SIZE = 64 + 1;
      char*rbuf = static_cast<char *>(need_result_buf(RBUF_USE_SIZE, RBUF_VAL));

      switch (val->format) {

	  case vpiObjTypeVal:
	    val->format = vpiStringVal;
	    // fall through
	  case vpiBinStrVal:
	  case vpiDecStrVal:
	  case vpiOctStrVal:
	  case vpiHexStrVal:
	  case vpiStringVal:
	    snprintf(rbuf, RBUF_USE_SIZE, "null");
	    val->value.str = rbuf;
	    break;

          case vpiScalarVal:
	    val->value.scalar = vpi0;
	    break;

	  case vpiIntVal:
	    val->value.integer = 0;
	    break;

	  case vpiVectorVal:
	    val->value.vector = static_cast<p_vpi_vecval>
	                        (need_result_buf(2*sizeof(s_vpi_vecval),
	                                         RBUF_VAL));
	    for (unsigned idx = 0; idx < 2; idx += 1) {
		  val->value.vector[idx].aval = 0;
		  val->value.vector[idx].bval = 0;
	    }
	    break;

	  case vpiRealVal:
	    val->value.real = 0.0;
	    break;

	  default:
	    fprintf(stderr, "vvp error: format %d not supported "
		    "by vpiNullConst\n", (int)val->format);
	    val->format = vpiSuppressVal;
	    break;
      }
}

vpiHandle vpip_make_null_const()
{
      __vpiNullConst*obj = new __vpiNullConst;
      return obj;
}

#ifdef CHECK_WITH_VALGRIND
void constant_delete(vpiHandle item)
{
      assert(item->get_type_code() == vpiConstant);
      switch(vpi_get(vpiConstType, item)) {
	  case vpiStringConst:
	    delete dynamic_cast<__vpiStringConst*>(item);
	    break;
	  case vpiDecConst:
	    delete dynamic_cast<__vpiDecConst*>(item);
	    break;
	  case vpiBinaryConst:
	    delete dynamic_cast<__vpiBinaryConst*>(item);
	    break;
	  case vpiRealConst:
	    delete dynamic_cast<__vpiRealConst*>(item);
	    break;
	  case vpiNullConst:
	    delete dynamic_cast<__vpiNullConst*>(item);
	    break;
	  default:
	    assert(0);
      }
}

void parameter_delete(vpiHandle item)
{
      switch(vpi_get(vpiConstType, item)) {
	  case vpiStringConst: {
	    class __vpiStringParam*rfp = dynamic_cast<__vpiStringParam*>(item);
	    delete rfp;
	    break; }
	  case vpiBinaryConst: {
	    struct __vpiBinaryParam*rfp = dynamic_cast<__vpiBinaryParam*>(item);
	    delete rfp;
	    break; }
	  case vpiRealConst: {
	    struct __vpiRealParam*rfp = dynamic_cast<__vpiRealParam*>(item);
	    delete rfp;
	    break; }
	  default:
	    assert(0);
      }
}
#endif

#include <map>
#include <typeinfo>
#include "schedule.h"
struct robotron_parameter_record {
    const char*name;size_t name_bytes;
    const char*string_value;size_t string_bytes;
    unsigned width;const unsigned long*a;const unsigned long*b;
};
static std::map<vpiHandle,robotron_parameter_record>&robotron_parameters()
{static std::map<vpiHandle,robotron_parameter_record> registry;return registry;}
extern "C" int robotron_vvp_parameter_owners(std::map<const void*,std::pair<unsigned long long,const void*>>*);
struct robotron_parameter_access {
    struct metadata {__vpiScope*scope;const char*name;bool local;unsigned file,line;};
    template<class T>static metadata meta(T*p){return {p->scope_,p->basename_,p->local_flag_,p->file_idx_,p->lineno_};}
    static metadata fields(vpiHandle p){
        if(typeid(*p)==typeid(__vpiBinaryParam))return meta(static_cast<__vpiBinaryParam*>(p));
        if(typeid(*p)==typeid(__vpiStringParam))return meta(static_cast<__vpiStringParam*>(p));
        return meta(static_cast<__vpiRealParam*>(p));
    }
    static void attach(vpiHandle p){
        // Refuse unknown concrete classes before any class-specific metadata read.
        // Scope ownership still records the object; inventory population checks
        // will reject the unadmitted parameter before writing a header.
        if(typeid(*p)!=typeid(__vpiBinaryParam) && typeid(*p)!=typeid(__vpiStringParam) && typeid(*p)!=typeid(__vpiRealParam)){
            ++robotron_parameter_unsupported;return;
        }
        robotron_parameter_record r={};auto m=fields(p);r.name=m.name;r.name_bytes=strlen(m.name)+1;
        if(typeid(*p)==typeid(__vpiBinaryParam)){
            auto&v=static_cast<__vpiBinaryParam*>(p)->bits;r.width=v.size_;
            if(v.size_>vvp_vector4_t::BITS_PER_WORD){r.a=v.abits_ptr_;r.b=v.bbits_ptr_;}
        }else if(typeid(*p)==typeid(__vpiStringParam)){
            auto s=static_cast<__vpiStringParam*>(p);r.string_value=s->value_;r.string_bytes=s->value_len_+1;
        }
        robotron_parameters()[p]=r;
    }
    static int hex(FILE*out,const char*tag,const void*address,size_t bytes){
        if(fprintf(out,"%s ",tag)<0)return -1;
        auto data=static_cast<const unsigned char*>(address);
        for(size_t i=0;i<bytes;++i)if(fprintf(out,"%02x",data[i])<0)return -1;
        return fputc('\n',out)==EOF?-1:0;
    }
    template<class T>static void metadata_fault(T*p,unsigned field){
        if(field==3)p->local_flag_=!p->local_flag_;
        else if(field==4)p->file_idx_^=1;
        else if(field==5)p->lineno_^=1;
        else if(field==6)const_cast<char*>(p->basename_)[0]^=1;
        else if(field==10)p->scope_=reinterpret_cast<__vpiScope*>(reinterpret_cast<uintptr_t>(p->scope_)^1);
        else if(field==11)p->basename_=reinterpret_cast<const char*>(reinterpret_cast<uintptr_t>(p->basename_)^1);
    }
    static int toggle(unsigned field){
        static vpiHandle saved=0;static unsigned saved_field=0;
        if(field>15 || (saved&&field!=saved_field))return -1;
        bool restoring=saved!=0;auto p=saved;
        if(!restoring){
            char*text=0;size_t size=0;FILE*out=open_memstream(&text,&size);if(!out)return -1;
            int rc=inventory(out);int close_rc=fclose(out);free(text);if(rc||close_rc)return -1;
            std::map<const void*,std::pair<unsigned long long,const void*>> owners;
            if(robotron_vvp_parameter_owners(&owners))return -1;
            unsigned long long first=~0ULL;
            for(auto entry:robotron_parameters()){
                auto item=entry.first;bool eligible=false;
                if(field==7)eligible=typeid(*item)==typeid(__vpiRealParam);
                else if(field==8||field==14||field==15)eligible=typeid(*item)==typeid(__vpiStringParam)&&entry.second.string_bytes>1;
                else if(typeid(*item)==typeid(__vpiBinaryParam))eligible=entry.second.width>0&&((field!=12&&field!=13)||entry.second.width>vvp_vector4_t::BITS_PER_WORD);
                if(eligible && owners.at(item).first<first){first=owners.at(item).first;p=item;}
            }
            if(!p)return -1;
        }
        if(field==7)reinterpret_cast<unsigned char*>(&static_cast<__vpiRealParam*>(p)->value)[0]^=1;
        else if(field==8)static_cast<__vpiStringParam*>(p)->value_[0]^=1;
        else if(field==14){auto s=static_cast<__vpiStringParam*>(p);s->value_=reinterpret_cast<char*>(reinterpret_cast<uintptr_t>(s->value_)^1);}
        else if(field==15)static_cast<__vpiStringParam*>(p)->value_len_^=1;
        else{
            auto b=static_cast<__vpiBinaryParam*>(p);auto&v=b->bits;
            if(field==0){if(v.size_>vvp_vector4_t::BITS_PER_WORD)v.abits_ptr_[0]^=1;else v.abits_val_^=1;}
            else if(field==1)b->signed_flag=!b->signed_flag;
            else if(field==2)b->sized_flag=!b->sized_flag;
            else if(field==9)v.size_^=1;
            else if(field==12)v.abits_ptr_=reinterpret_cast<unsigned long*>(reinterpret_cast<uintptr_t>(v.abits_ptr_)^1);
            else if(field==13)v.bbits_ptr_=reinterpret_cast<unsigned long*>(reinterpret_cast<uintptr_t>(v.bbits_ptr_)^1);
            else metadata_fault(b,field);
        }
        if(restoring)saved=0;else{saved=p;saved_field=field;}return 1;
    }
    static int inventory(FILE*out){
        std::map<const void*,std::pair<unsigned long long,const void*>> owners;
        if(!out||robotron_vvp_parameter_owners(&owners)||owners.size()!=robotron_parameters().size())return -1;
        std::map<unsigned long long,vpiHandle> ordered;
        for(auto entry:robotron_parameters()){
            auto p=entry.first;auto&r=entry.second;auto owner=owners.find(p);
            if(owner==owners.end() || (typeid(*p)!=typeid(__vpiBinaryParam)&&typeid(*p)!=typeid(__vpiStringParam)&&typeid(*p)!=typeid(__vpiRealParam)))return -1;
            auto m=fields(p);
            if(m.scope!=owner->second.second||m.name!=r.name||!r.name||!r.name_bytes)return -1;
            if(typeid(*p)==typeid(__vpiBinaryParam)){
                auto&v=static_cast<__vpiBinaryParam*>(p)->bits;
                if(v.size_!=r.width)return -1;
                if(v.size_>vvp_vector4_t::BITS_PER_WORD && (v.abits_ptr_!=r.a||v.bbits_ptr_!=r.b||!r.a||!r.b))return -1;
            }else if(typeid(*p)==typeid(__vpiStringParam)){
                auto s=static_cast<__vpiStringParam*>(p);
                if(s->value_!=r.string_value||s->value_len_+1!=r.string_bytes||!r.string_value||!r.string_bytes)return -1;
            }
            ordered[owner->second.first]=p;
        }
        if(fprintf(out,"VPM_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
        for(auto item:ordered){
            auto p=item.second;auto&r=robotron_parameters().at(p);auto m=fields(p);
            const char*kind=typeid(*p)==typeid(__vpiBinaryParam)?"binary":typeid(*p)==typeid(__vpiStringParam)?"string":"real";
            if(fprintf(out,"VPM_PARAM %llu %p %s %p %u %u %u %zu\n",item.first,(void*)p,kind,(void*)m.scope,unsigned(m.local),m.file,m.line,r.name_bytes)<0||hex(out,"VPM_NAME",r.name,r.name_bytes))return -1;
            if(typeid(*p)==typeid(__vpiBinaryParam)){
                auto b=static_cast<__vpiBinaryParam*>(p);auto&v=b->bits;unsigned words=v.size_>vvp_vector4_t::BITS_PER_WORD?(v.size_+vvp_vector4_t::BITS_PER_WORD-1)/vvp_vector4_t::BITS_PER_WORD:1;
                if(fprintf(out,"VPM_BINARY %u %u %u %u %u %p %p\n",v.size_,unsigned(b->signed_flag),unsigned(b->sized_flag),unsigned(vvp_vector4_t::BITS_PER_WORD),words,(void*)r.a,(void*)r.b)<0)return -1;
                for(unsigned i=0;i<words;++i){auto a=v.size_>vvp_vector4_t::BITS_PER_WORD?r.a[i]:v.abits_val_;auto b=v.size_>vvp_vector4_t::BITS_PER_WORD?r.b[i]:v.bbits_val_;
                    if(fprintf(out,"VPM_WORD %u %lx %lx\n",i,a,b)<0)return -1;
                }
            }else if(typeid(*p)==typeid(__vpiStringParam)){
                if(fprintf(out,"VPM_STRING %p %zu\n",(void*)r.string_value,r.string_bytes)<0||hex(out,"VPM_BYTES",r.string_value,r.string_bytes))return -1;
            }else{
                auto real=static_cast<__vpiRealParam*>(p);
                if(fprintf(out,"VPM_REAL %zu\n",sizeof(real->value))<0||hex(out,"VPM_BYTES",&real->value,sizeof(real->value)))return -1;
            }
        }
        return fprintf(out,"VPM_END %zu\n",ordered.size())<0||ferror(out)?-1:0;
    }
};
static void robotron_parameter_register(vpiHandle p){robotron_parameter_access::attach(p);}
extern "C" void robotron_vvp_memory_forget(vpiHandle);
static void robotron_parameter_unregister(vpiHandle p){
    robotron_parameters().erase(p);
    if(getenv("ROBOTRON_TEARDOWN_TRACE")) fprintf(stdout,"TEARDOWN_PARAMETER_REMAIN %zu\n",robotron_parameters().size());
    // Existing scope-registration invalidation is independent of object type.
    robotron_vvp_memory_forget(p);
}

extern "C" int robotron_vvp_parameter_inventory(FILE*out){
    if(!robotron_vvp_observation_active())return -1;
return robotron_parameter_access::inventory(out);}

extern "C" int robotron_vvp_parameter_toggle(unsigned field){return robotron_parameter_access::toggle(field);}

extern "C" int robotron_vvp_parameter_add(unsigned kind)
{
    if(kind>2)return -1;
    char*text=0;size_t size=0;FILE*out=open_memstream(&text,&size);if(!out)return -1;
    int rc=robotron_vvp_parameter_inventory(out);int closed=fclose(out);free(text);
    if(rc||closed)return -1;
    std::map<const void*,std::pair<unsigned long long,const void*>> owners;
    if(robotron_vvp_parameter_owners(&owners)||owners.empty())return -1;
    auto scope=static_cast<__vpiScope*>(const_cast<void*>(owners.begin()->second.second));
    static unsigned serial;char buffer[80];snprintf(buffer,sizeof(buffer),"__growth_%u_%u",kind,++serial);
    char*name=new char[strlen(buffer)+1];strcpy(name,buffer);vpiHandle parameter;
    if(kind==0){vvp_vector4_t value(80,BIT4_X);value.set_bit(0,BIT4_1);parameter=new __vpiBinaryParam(scope,value,false,name,false,0,0);}
    else if(kind==1)parameter=new __vpiRealParam(scope,2.5,name,false,0,0);
    else{const char*encoded="G\\000R";char*value=new char[strlen(encoded)+1];strcpy(value,encoded);parameter=new __vpiStringParam(scope,value,name,false,0,0);}
    robotron_parameter_register(parameter);vpip_attach_to_scope(scope,parameter);return 1;
}

extern "C" int robotron_vvp_parameter_add_unsupported(unsigned kind)
{
    if(kind>2)return -1;
    char*text=0;size_t size=0;FILE*out=open_memstream(&text,&size);if(!out)return -1;
    int rc=robotron_vvp_parameter_inventory(out);int closed=fclose(out);free(text);
    if(rc||closed)return -1;
    std::map<const void*,std::pair<unsigned long long,const void*>> owners;
    if(robotron_vvp_parameter_owners(&owners)||owners.empty())return -1;
    auto scope=static_cast<__vpiScope*>(const_cast<void*>(owners.begin()->second.second));
    static unsigned serial;char buffer[80];snprintf(buffer,sizeof(buffer),"__unsupported_%u_%u",kind,++serial);
    char*name=new char[strlen(buffer)+1];strcpy(name,buffer);vpiHandle parameter;
    if(kind==0){vvp_vector4_t value(80,BIT4_X);value.set_bit(0,BIT4_1);parameter=new robotron_binary_param_extra(scope,value,false,name,false,0,0);}
    else if(kind==1)parameter=new robotron_real_param_extra(scope,2.5,name,false,0,0);
    else{const char*encoded="G\\000R";char*value=new char[strlen(encoded)+1];strcpy(value,encoded);parameter=new robotron_string_param_extra(scope,value,name,false,0,0);}
    robotron_parameter_register(parameter);vpip_attach_to_scope(scope,parameter);return 1;
}

#include <new>
extern "C" int robotron_vvp_parameter_lifecycle(unsigned operation,unsigned kind)
{
    static void*storage=0;static vpiHandle live=0,stale=0;static __vpiScope*scope=0;
    static unsigned live_kind=0,serial=0;
    if(kind>2)return -1;
    if(operation==0){
        if(live||stale)return -1;
        std::map<const void*,std::pair<unsigned long long,const void*>> owners;
        if(robotron_vvp_parameter_owners(&owners)||owners.empty())return -1;
        scope=static_cast<__vpiScope*>(const_cast<void*>(owners.begin()->second.second));
        if(!storage){size_t n=sizeof(__vpiBinaryParam);if(n<sizeof(__vpiRealParam))n=sizeof(__vpiRealParam);if(n<sizeof(__vpiStringParam))n=sizeof(__vpiStringParam);storage=::operator new(n);}
        char buffer[80];snprintf(buffer,sizeof(buffer),"__parameter_lifecycle_%u_%u",kind,++serial);
        char*name=new char[strlen(buffer)+1];strcpy(name,buffer);
        if(kind==0){vvp_vector4_t value(80,BIT4_X);value.set_bit(0,BIT4_1);live=new(storage)__vpiBinaryParam(scope,value,false,name,false,0,0);}
        else if(kind==1)live=new(storage)__vpiRealParam(scope,2.5,name,false,0,0);
        else{const char*encoded="G\\000R";char*value=new char[strlen(encoded)+1];strcpy(value,encoded);live=new(storage)__vpiStringParam(scope,value,name,false,0,0);}
        robotron_parameter_register(live);vpip_attach_to_scope(scope,live);live_kind=kind;return 1;
    }
    if(operation==1){
        if(!live||stale||kind!=live_kind)return -1;
        stale=live;
        if(kind==0)static_cast<__vpiBinaryParam*>(live)->~__vpiBinaryParam();
        else if(kind==1)static_cast<__vpiRealParam*>(live)->~__vpiRealParam();
        else static_cast<__vpiStringParam*>(live)->~__vpiStringParam();
        live=0;return 1;
    }
    if(operation==2){
        if(live||!stale||kind!=live_kind)return -1;
        auto found=std::find(scope->intern.begin(),scope->intern.end(),stale);
        if(found==scope->intern.end())return -1;
        scope->intern.erase(found);stale=0;return 1;
    }
    return -1;
}

extern "C" int robotron_vvp_parameter_refusal_cycle(unsigned operation,unsigned kind)
{
    static vpiHandle live=0,stale=0;static __vpiScope*scope=0;static unsigned live_kind=0;
    if(kind>2)return -1;
    if(operation==0){
        if(live||stale)return -1;
        std::map<const void*,std::pair<unsigned long long,const void*>> before,after;
        if(robotron_vvp_parameter_owners(&before)||before.empty())return -1;
        if(robotron_vvp_parameter_add_unsupported(kind)!=1)return -1;
        if(robotron_vvp_parameter_owners(&after)||after.size()!=before.size()+1)abort();
        for(auto item:after)if(!before.count(item.first)){
            if(live)abort();live=static_cast<vpiHandle>(const_cast<void*>(item.first));
            scope=static_cast<__vpiScope*>(const_cast<void*>(item.second.second));
        }
        if(!live || (kind==0 && typeid(*live)!=typeid(robotron_binary_param_extra)) ||
           (kind==1 && typeid(*live)!=typeid(robotron_real_param_extra)) ||
           (kind==2 && typeid(*live)!=typeid(robotron_string_param_extra)))abort();
        live_kind=kind;return 1;
    }
    if(operation==1){
        if(!live||stale||kind!=live_kind)return -1;
        stale=live;delete live;live=0;return 1;
    }
    if(operation==2){
        if(live||!stale||kind!=live_kind)return -1;
        auto found=std::find(scope->intern.begin(),scope->intern.end(),stale);
        if(found==scope->intern.end())return -1;
        scope->intern.erase(found);stale=0;return 1;
    }
    return -1;
}
