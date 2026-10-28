extern "C" int robotron_vvp_observation_active();
/*
 * Copyright (c) 2001-2016 Stephen Williams (steve@icarus.com)
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

# include  "codes.h"
# include  "statistics.h"
# include  "config.h"
#ifdef CHECK_WITH_VALGRIND
# include  "vvp_cleanup.h"
#endif
# include  <cstring>
# include  <cassert>

/*
 * The code space is broken into chunks, to make for efficient
 * allocation of large amounts. Each chunk is an array of vvp_code_s
 * structures, with the last opcode loaded with an of_CHUNK_LINK
 * instruction to branch to the next chunk. This handles the case
 * where the program counter steps off the end of a chunk.
 */
const unsigned code_chunk_size = 1024;

#include <vector>
#include <cstdint>
struct robotron_code_chunk {vvp_code_t base;unsigned used;};
static std::vector<robotron_code_chunk>& robotron_code_chunks()
{static std::vector<robotron_code_chunk> chunks;return chunks;}
static struct vvp_code_s *first_chunk = 0;
static struct vvp_code_s *current_chunk = 0;
static unsigned current_within_chunk = 0;

/*
 * This initializes the code space. It sets up the first code chunk,
 * and places at address 0 a ZOMBIE instruction.
 */
void codespace_init(void)
{
      assert(current_chunk == 0);
      first_chunk = new struct vvp_code_s [code_chunk_size];
      current_chunk = first_chunk;

      current_chunk[0].opcode = &of_ZOMBIE;

      current_chunk[code_chunk_size-1].opcode = &of_CHUNK_LINK;
      current_chunk[code_chunk_size-1].cptr = 0;

      current_within_chunk = 1;
      robotron_code_chunks().push_back({current_chunk,1});

      count_opcodes = 0;
      size_opcodes += code_chunk_size * sizeof (struct vvp_code_s);
}

vvp_code_t codespace_next(void)
{
      if (current_within_chunk == (code_chunk_size-1)) {
	    current_chunk[code_chunk_size-1].cptr
		  = new struct vvp_code_s [code_chunk_size];
	    current_chunk = current_chunk[code_chunk_size-1].cptr;

	      /* Put a link opcode on the end of the chunk. */
	    current_chunk[code_chunk_size-1].opcode = &of_CHUNK_LINK;
	    current_chunk[code_chunk_size-1].cptr   = 0;

	    current_within_chunk = 0;
            robotron_code_chunks().push_back({current_chunk,0});

	    size_opcodes += code_chunk_size * sizeof (struct vvp_code_s);
      }

      vvp_code_t res = current_chunk + current_within_chunk;
      return res;
}

vvp_code_t codespace_allocate(void)
{
      vvp_code_t res = codespace_next();
      current_within_chunk += 1;
      count_opcodes += 1;

      memset(res, 0, sizeof(*res));
      robotron_code_chunks().back().used=current_within_chunk;

      return res;
}

vvp_code_t codespace_null(void)
{
      return first_chunk + 0;
}

#ifdef CHECK_WITH_VALGRIND
void codespace_delete(void)
{
      robotron_code_chunks().clear();
      vvp_code_t cur = first_chunk;

	/* If there are no opcodes then just delete the code space. */
      if (count_opcodes == 0) {
	    delete [] cur;
	    return;
      }

      do {
	    vvp_code_t next = cur[code_chunk_size-1].cptr;
	    for (unsigned idx = 0 ; idx < code_chunk_size; idx += 1) {
		  count_opcodes -= 1;
		  if ((cur+idx)->opcode == &of_VPI_CALL) {
			vpi_call_delete((cur+idx)->handle);
		  } else if (((cur+idx)->opcode == &of_EXEC_UFUNC_REAL) ||
		             ((cur+idx)->opcode == &of_EXEC_UFUNC_VEC4)) {
			exec_ufunc_delete((cur+idx));
		  } else if ((cur+idx)->opcode == &of_FILE_LINE) {
			delete((cur+idx)->handle);
		  } else if (((cur+idx)->opcode == &of_CONCATI_STR) ||
		             ((cur+idx)->opcode == &of_NEW_DARRAY) ||
		             ((cur+idx)->opcode == &of_PUSHI_STR)) {
			delete [] ((cur+idx)->text);
		  }
		  if (count_opcodes == 0) break;
	    }
	      /* Don't count the &of_CHUNK_LINK opcode. */
	    if (count_opcodes != 0) count_opcodes += 1;
	    delete [] cur;
	    cur = next;
      } while (cur != 0);
}
#endif

// Validate against separately registered allocated slots before dereferencing.
// Unused chunk capacity is not an instruction. Chunk links and ZOMBIE are
// initialized specially and only their opcode is observed here.
extern "C" unsigned long long robotron_vvp_code_identity(vvp_code_t code,void**opcode)
{
    *opcode=0;uintptr_t address=reinterpret_cast<uintptr_t>(code);
    const auto&chunks=robotron_code_chunks();
    for(size_t i=0;i<chunks.size();++i) {
        uintptr_t base=reinterpret_cast<uintptr_t>(chunks[i].base);
        if(address<base || address-base>=code_chunk_size*sizeof(vvp_code_s))continue;
        uintptr_t offset=address-base;
        if(offset%sizeof(vvp_code_s))return 0;
        unsigned index=offset/sizeof(vvp_code_s);
        if(index>=chunks[i].used && index!=code_chunk_size-1)return 0;
        *opcode=reinterpret_cast<void*>(code->opcode);
        return i*code_chunk_size+index+1;
    }
    return 0;
}

// Full typed scans with a fixed reference image; no hashes or active-PC shortcut.
#include <sstream>
#include <string>
#include <map>
#include "schedule.h"
static std::string robotron_code_ref(vvp_code_t code)
{
    void* opcode=0;
    auto id=robotron_vvp_code_identity(code,&opcode);
    std::ostringstream out;out<<reinterpret_cast<uintptr_t>(code)<<"/"<<id;return out.str();
}
static bool robotron_operand_row(vvp_code_t code,std::ostringstream& row,unsigned& mask)
{
    if(code->opcode==&of_ADD) { row<<"of_ADD"; mask=0; return true; }
    if(code->opcode==&of_ADDI) { row<<"of_ADDI"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_AND) { row<<"of_AND"; mask=0; return true; }
    if(code->opcode==&of_ASSIGN_VEC4) { row<<"of_ASSIGN_VEC4"; row<<" net="<<reinterpret_cast<uintptr_t>(code->net); row<<" bit_idx[0]="<<code->bit_idx[0]; mask=0; return true; }
    if(code->opcode==&of_ASSIGN_VEC4_A_D) { row<<"of_ASSIGN_VEC4_A_D"; row<<" array="<<reinterpret_cast<uintptr_t>(code->array); row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=0; return true; }
    if(code->opcode==&of_ASSIGN_VEC4_OFF_D) { row<<"of_ASSIGN_VEC4_OFF_D"; row<<" net="<<reinterpret_cast<uintptr_t>(code->net); row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=0; return true; }
    if(code->opcode==&of_BLEND) { row<<"of_BLEND"; mask=0; return true; }
    if(code->opcode==&of_CALLF_VEC4) { row<<"of_CALLF_VEC4"; row<<" cptr2="<<robotron_code_ref(code->cptr2); row<<" handle="<<reinterpret_cast<uintptr_t>(code->handle); mask=12; return true; }
    if(code->opcode==&of_CHUNK_LINK) { row<<"of_CHUNK_LINK"; row<<" cptr="<<robotron_code_ref(code->cptr); mask=2; return true; }
    if(code->opcode==&of_CMPE) { row<<"of_CMPE"; mask=0; return true; }
    if(code->opcode==&of_CMPIE) { row<<"of_CMPIE"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_CMPINE) { row<<"of_CMPINE"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_CMPIU) { row<<"of_CMPIU"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_CMPNE) { row<<"of_CMPNE"; mask=0; return true; }
    if(code->opcode==&of_CMPU) { row<<"of_CMPU"; mask=0; return true; }
    if(code->opcode==&of_CMPZ) { row<<"of_CMPZ"; mask=0; return true; }
    if(code->opcode==&of_CONCATI_VEC4) { row<<"of_CONCATI_VEC4"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_CONCAT_VEC4) { row<<"of_CONCAT_VEC4"; mask=0; return true; }
    if(code->opcode==&of_DELAY) { row<<"of_DELAY"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=0; return true; }
    if(code->opcode==&of_DUP_VEC4) { row<<"of_DUP_VEC4"; mask=0; return true; }
    if(code->opcode==&of_END) { row<<"of_END"; mask=0; return true; }
    if(code->opcode==&of_FLAG_GET_VEC4) { row<<"of_FLAG_GET_VEC4"; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_FLAG_INV) { row<<"of_FLAG_INV"; row<<" bit_idx[0]="<<code->bit_idx[0]; mask=0; return true; }
    if(code->opcode==&of_FLAG_MOV) { row<<"of_FLAG_MOV"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=0; return true; }
    if(code->opcode==&of_FLAG_OR) { row<<"of_FLAG_OR"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=0; return true; }
    if(code->opcode==&of_FLAG_SET_IMM) { row<<"of_FLAG_SET_IMM"; row<<" number="<<code->number; row<<" bit_idx[0]="<<code->bit_idx[0]; mask=1; return true; }
    if(code->opcode==&of_FLAG_SET_VEC4) { row<<"of_FLAG_SET_VEC4"; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_FORK) { row<<"of_FORK"; row<<" cptr2="<<robotron_code_ref(code->cptr2); row<<" handle="<<reinterpret_cast<uintptr_t>(code->handle); mask=12; return true; }
    if(code->opcode==&of_INV) { row<<"of_INV"; mask=0; return true; }
    if(code->opcode==&of_IX_LOAD) { row<<"of_IX_LOAD"; row<<" number="<<code->number; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=1; return true; }
    if(code->opcode==&of_IX_VEC4) { row<<"of_IX_VEC4"; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_JMP) { row<<"of_JMP"; row<<" cptr="<<robotron_code_ref(code->cptr); mask=2; return true; }
    if(code->opcode==&of_JMP0) { row<<"of_JMP0"; row<<" cptr="<<robotron_code_ref(code->cptr); row<<" bit_idx[0]="<<code->bit_idx[0]; mask=2; return true; }
    if(code->opcode==&of_JMP0XZ) { row<<"of_JMP0XZ"; row<<" cptr="<<robotron_code_ref(code->cptr); row<<" bit_idx[0]="<<code->bit_idx[0]; mask=2; return true; }
    if(code->opcode==&of_JMP1) { row<<"of_JMP1"; row<<" cptr="<<robotron_code_ref(code->cptr); row<<" bit_idx[0]="<<code->bit_idx[0]; mask=2; return true; }
    if(code->opcode==&of_JOIN) { row<<"of_JOIN"; mask=0; return true; }
    if(code->opcode==&of_LOAD_VEC4) { row<<"of_LOAD_VEC4"; row<<" net="<<reinterpret_cast<uintptr_t>(code->net); mask=0; return true; }
    if(code->opcode==&of_MOD_S) { row<<"of_MOD_S"; mask=0; return true; }
    if(code->opcode==&of_MUL_WR) { row<<"of_MUL_WR"; mask=0; return true; }
    if(code->opcode==&of_NORR) { row<<"of_NORR"; mask=0; return true; }
    if(code->opcode==&of_OR) { row<<"of_OR"; mask=0; return true; }
    if(code->opcode==&of_PAD_U) { row<<"of_PAD_U"; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_PARTI_S) { row<<"of_PARTI_S"; row<<" number="<<code->number; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=1; return true; }
    if(code->opcode==&of_POP_VEC4) { row<<"of_POP_VEC4"; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_PUSHI_REAL) { row<<"of_PUSHI_REAL"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=0; return true; }
    if(code->opcode==&of_PUSHI_VEC4) { row<<"of_PUSHI_VEC4"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_REPLICATE) { row<<"of_REPLICATE"; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_RET_VEC4) { row<<"of_RET_VEC4"; row<<" number="<<code->number; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=1; return true; }
    if(code->opcode==&of_STORE_VEC4) { row<<"of_STORE_VEC4"; row<<" net="<<reinterpret_cast<uintptr_t>(code->net); row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; mask=0; return true; }
    if(code->opcode==&of_SUBI) { row<<"of_SUBI"; row<<" bit_idx[0]="<<code->bit_idx[0]; row<<" bit_idx[1]="<<code->bit_idx[1]; row<<" number="<<code->number; mask=1; return true; }
    if(code->opcode==&of_VPI_CALL) { row<<"of_VPI_CALL"; row<<" handle="<<reinterpret_cast<uintptr_t>(code->handle); mask=8; return true; }
    if(code->opcode==&of_WAIT) { row<<"of_WAIT"; row<<" net="<<reinterpret_cast<uintptr_t>(code->net); mask=0; return true; }
    if(code->opcode==&of_XOR) { row<<"of_XOR"; mask=0; return true; }
    if(code->opcode==&of_XORR) { row<<"of_XORR"; mask=0; return true; }
    if(code->opcode==&of_ZOMBIE) { row<<"of_ZOMBIE"; mask=0; return true; }
    return false;
}
struct robotron_operand_entry {unsigned long long id;vvp_code_t code;unsigned mask;std::string row;};
static bool robotron_operand_scan(std::vector<robotron_operand_entry>& rows)
{
    const auto& chunks=robotron_code_chunks();
    for(size_t i=0;i<chunks.size();++i) {
        for(unsigned index=0;index<code_chunk_size;++index) {
            if(index>=chunks[i].used && index!=code_chunk_size-1)continue;
            vvp_code_t code=chunks[i].base+index;unsigned mask=0;
            auto id=i*code_chunk_size+index+1;
            std::ostringstream row;row<<"VCO_ROW "<<id<<" ";
            if(!robotron_operand_row(code,row,mask))return false;
            rows.push_back({id,code,mask,row.str()});
        }
    }
    return !rows.empty();
}
static std::vector<robotron_operand_entry>& robotron_operand_reference()
{static std::vector<robotron_operand_entry> rows;return rows;}
static int robotron_operand_write(FILE* out,char mode,const std::vector<robotron_operand_entry>& rows)
{
    const auto& reference=robotron_operand_reference();
    if(!out)return -1;
    if(mode=='D' && rows.size()!=reference.size())return -1;
    size_t changed=0;
    for(size_t i=0;i<rows.size();++i) {
        if(mode=='D' && (rows[i].id!=reference[i].id || rows[i].code!=reference[i].code))return -1;
        if(mode!='D' || rows[i].row!=reference[i].row)++changed;
    }
    if(fprintf(out,"VCO_BEGIN %c %llu %zu %zu\n",mode,(unsigned long long)schedule_simtime(),rows.size(),changed)<0)return -1;
    for(size_t i=0;i<rows.size();++i)
        if(mode!='D' || rows[i].row!=reference[i].row)
            if(fprintf(out,"%s\n",rows[i].row.c_str())<0)return -1;
    return fprintf(out,"VCO_END %zu\n",changed)<0 || ferror(out)?-1:0;
}
extern "C" int robotron_vvp_code_operand_reference(FILE* out)
{
    auto& reference=robotron_operand_reference();
    if(!out || !reference.empty())return -1;
    std::vector<robotron_operand_entry> rows;
    if(!robotron_operand_scan(rows))return -1;
    int result=robotron_operand_write(out,'R',rows);
    if(!result)reference.swap(rows);
    return result;
}
extern "C" int robotron_vvp_code_operand_inventory(FILE* out,int sparse)
{
    if(!robotron_vvp_observation_active())return -1;

    if(sparse!=0 && sparse!=1)return -1;
    std::vector<robotron_operand_entry> rows;
    if(!robotron_operand_scan(rows))return -1;
    if(sparse && robotron_operand_reference().empty())return -1;
    return robotron_operand_write(out,sparse?'D':'F',rows);
}
extern "C" int robotron_vvp_code_operand_toggle(int field)
{
    static vvp_code_t saved=0;static unsigned long long identity=0;static int saved_field=0;
    static unsigned long number=0;static vvp_code_t target=0;static __vpiHandle* handle=0;static vvp_code_fun opcode=0;
    if(saved) {
        void* current=0;
        if(field!=saved_field || robotron_vvp_code_identity(saved,&current)!=identity)return -1;
        if(field==0)saved->number=number;
        else if(field==1)saved->cptr=target;
        else if(field==2)saved->handle=handle;
        else if(field==3)saved->opcode=opcode;
        saved=0;return 1;
    }
    if(field<0 || field>3)return -1;
    std::vector<robotron_operand_entry> rows;
    if(!robotron_operand_scan(rows))return -1;
    unsigned need=field==0?1:field==1?2:field==2?8:0;
    for(const auto& entry:rows) {
        if(field!=3 && !(entry.mask&need))continue;
        saved=entry.code;identity=entry.id;saved_field=field;
        if(field==0){number=saved->number;saved->number^=1;}
        else if(field==1){target=saved->cptr;saved->cptr=reinterpret_cast<vvp_code_t>(1);}
        else if(field==2){handle=saved->handle;saved->handle=reinterpret_cast<__vpiHandle*>(1);}
        else {opcode=saved->opcode;saved->opcode=&of_ABS_WR;}
        return 1;
    }
    return 0;
}
