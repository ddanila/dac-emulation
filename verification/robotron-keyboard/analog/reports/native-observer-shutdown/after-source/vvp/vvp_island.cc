extern "C" int robotron_vvp_observation_active();
/*
 * Copyright (c) 2008-2025 Stephen Williams (steve@icarus.com)
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

# include  "vvp_island.h"
# include  "compile.h"
# include  "symbols.h"
# include  "schedule.h"
# include  "config.h"
#ifdef CHECK_WITH_VALGRIND
# include  "vvp_cleanup.h"
#endif
# include  <iostream>
# include  <list>
# include  <cassert>
# include  <cstdlib>
# include  <cstring>
# include "ivl_alloc.h"

using namespace std;

#include <map>
#include <vector>
struct robotron_island_record {
    unsigned long long id;
    std::vector<vvp_net_t*> ports;
    std::vector<vvp_island_branch*> branches;
};
static std::map<vvp_island*,robotron_island_record>& robotron_islands()
{ static std::map<vvp_island*,robotron_island_record> value;return value; }
static unsigned long long robotron_island_serial=0;
extern int robotron_tran_inventory(FILE*,vvp_island_branch*);
extern int robotron_tran_toggle(vvp_island_branch*);
static int robotron_island_vector(FILE* out,const char* name,const vvp_vector8_t& value)
{
    if(fprintf(out,"VI_VECTOR %s %u ",name,value.size())<0)return -1;
    if(!value.size() && fputc('-',out)==EOF)return -1;
    for(unsigned i=0;i<value.size();++i){
        auto b=value.value(i);
        if(fprintf(out,"%u%u%u",(unsigned)b.value(),b.strength0(),b.strength1())<0)return -1;
    }
    return fputc('\n',out)==EOF?-1:0;
}


#ifdef CHECK_WITH_VALGRIND
static bool at_EOS = false;
#endif

void island_send_value(vvp_net_t*net, const vvp_vector8_t&val)
{
      vvp_island_port*fun = dynamic_cast<vvp_island_port*>(net->fun);
      if (fun->outvalue .eeq(val))
	    return;

      fun->outvalue = val;
      net->send_vec8(fun->outvalue);
}

/*
 * Implementations...
 */
vvp_island::vvp_island()
{
      flagged_ = false;
      branches_ = 0;
      ports_ = 0;
      anodes_ = 0;
      bnodes_ = 0;
      robotron_islands()[this]={++robotron_island_serial,{}, {}};
}

vvp_island::~vvp_island()
{
      robotron_islands().erase(this);
	// We can only delete islands at the end of simulation.
#ifdef CHECK_WITH_VALGRIND
      if (!at_EOS) assert(0);
#endif

      while (branches_) {
	    vvp_island_branch *next_br = branches_->next_branch;
	    delete branches_;
	    branches_ = next_br;
      }
}

void vvp_island::flag_island()
{
      if (flagged_ == true)
	    return;

      schedule_generic(this, 0, false, false);
      flagged_ = true;
}

/*
* This method handles the callback from the scheduler. It does basic
* housecleaning and calls the run_island() method implemented by the
* derived class.
*/
void vvp_island::run_run()
{
      flagged_ = false;
      run_island();
}


void vvp_island::add_port(const char*key, vvp_net_t*net)
{
      if (ports_ == 0)
	    ports_ = new symbol_map_s<vvp_net_t>;

	// each port should have a unique label
      assert(ports_->sym_get_value(key) == 0);

      ports_->sym_set_value(key, net);
      robotron_islands().at(this).ports.push_back(net);
}

void vvp_island::add_branch(vvp_island_branch*branch, const char*pa, const char*pb)
{
      vvp_island_branch*cur;
      assert(ports_);
      branch->a = ports_->sym_get_value(pa);
      branch->b = ports_->sym_get_value(pb);
      assert(branch->a && branch->b);

      vvp_branch_ptr_t ptra (branch, 0);
      vvp_branch_ptr_t ptrb (branch, 1);
      if (anodes_ == 0)
	    anodes_ = new symbol_map_s<vvp_island_branch>;
      if (bnodes_ == 0)
	    bnodes_ = new symbol_map_s<vvp_island_branch>;

      if ((cur = anodes_->sym_get_value(pa))) {
	    branch->link[0] = cur->link[0];
	    cur->link[0] = ptra;
      } else if ((cur = bnodes_->sym_get_value(pa))) {
	    branch->link[0] = cur->link[1];
	    cur->link[1] = ptra;
      } else {
	    branch->link[0] = ptra;
	    anodes_->sym_set_value(pa, branch);
      }

      if ((cur = anodes_->sym_get_value(pb))) {
	    branch->link[1] = cur->link[0];
	    cur->link[0] = ptrb;
      } else if ((cur = bnodes_->sym_get_value(pb))) {
	    branch->link[1] = cur->link[1];
	    cur->link[1] = ptrb;
      } else {
	    branch->link[1] = ptrb;
	    bnodes_->sym_set_value(pb, branch);
      }

      branch->next_branch = branches_;
      branches_ = branch;
      robotron_islands().at(this).branches.push_back(branch);
}

vvp_net_t* vvp_island::find_port(const char*key)
{
      if (ports_ == 0)
	    return 0;
      else
	    return ports_->sym_get_value(key);
}

void vvp_island::compile_cleanup()
{
      delete ports_;
      ports_ = 0;

      delete anodes_;
      anodes_ = 0;

      delete bnodes_;
      bnodes_ = 0;
}

vvp_island_port::vvp_island_port(vvp_island*ip)
: island_(ip)
{
}

vvp_island_port::~vvp_island_port()
{
}

void vvp_island_port::recv_vec4(vvp_net_ptr_t, const vvp_vector4_t&bit,
                                vvp_context_t)
{
      vvp_vector8_t tmp (bit, 6, 6);
      if (invalue .eeq(tmp))
	    return;

      invalue = tmp;
      island_->flag_island();
}

void vvp_island_port::recv_vec4_pv(vvp_net_ptr_t port, const vvp_vector4_t&bit,
				   unsigned base, unsigned vwid, vvp_context_t)
{
      vvp_vector8_t tmp(bit, 6, 6);
      recv_vec8_pv(port, tmp, base, vwid);
}


void vvp_island_port::recv_vec8(vvp_net_ptr_t, const vvp_vector8_t&bit)
{
      if (invalue .eeq(bit))
	    return;

      invalue = bit;
      island_->flag_island();
}

void vvp_island_port::recv_vec8_pv(vvp_net_ptr_t, const vvp_vector8_t&bit,
                                   unsigned base, unsigned vwid)
{
      if (invalue.size() == 0) {
	    invalue = part_expand(bit, vwid, base);
      } else {
	    unsigned wid = bit.size();
	    assert(invalue.size() == vwid);
	    for (unsigned idx = 0; idx < wid ; idx += 1) {
		  if ((base+idx) >= vwid)
			break;
		  invalue.set_bit(base+idx, bit.value(idx));
	    }
      }

      island_->flag_island();
}

void vvp_island_port::force_flag(bool run_now)
{
      if (run_now)
	    island_->run_island();
      else
	    island_->flag_island();
}

vvp_island_branch::~vvp_island_branch()
{
}

void island_collect_node(list<vvp_branch_ptr_t>&conn, vvp_branch_ptr_t cur)
{
      conn .push_back(cur);
      for (vvp_branch_ptr_t idx = next(cur) ; idx != cur ; idx = next(idx))
	    conn.push_back(idx);
}

/* **** COMPILE/LINK SUPPORT **** */

/*
* We need to keep an island symbol table to make island labels to
* islands, and we need a list of the islands that we can run through
* during cleanup. After linking is done, the compile_island_cleanup() is
* called to erase the symbol table, we still need the list to cleanup the
* island memory at EOS.
*/
static symbol_map_s<vvp_island>* island_table = 0;
static vvp_island** island_list = 0;
static unsigned island_count = 0;

#ifdef CHECK_WITH_VALGRIND
void island_delete()
{
      at_EOS = true;
      for (unsigned idx = 0; idx < island_count; idx += 1) {
	    delete island_list[idx];
      }
      free(island_list);
      island_list = 0;
      island_count = 0;
}
#endif

void compile_island_base(char*label, vvp_island*use_island)
{
      if (island_table == 0)
	    island_table = new symbol_map_s<vvp_island>;

      island_table->sym_set_value(label, use_island);
      island_count += 1;
      island_list = static_cast<vvp_island **>(realloc(island_list,
                                               island_count*sizeof(vvp_island **)));
      island_list[island_count-1] = use_island;
      free(label);
}

vvp_island* compile_find_island(const char*island)
{
      assert(island_table);
      vvp_island*use_island = island_table->sym_get_value(island);
      assert(use_island);
      return use_island;
}

/*
 * This handles the compile of a .port record. A .port is a 2-way port
 * between the island and the outside. For example,
 *
 *   <label> .port <island> <src> ;
 *
 * The <src> is a label in the domain outside the island, and the
 * <label> is in the domain inside the island. Since this port is
 * bi-directional, the <label> is also available in the domain outside
 * the island. The outside should use the <label> to access the nexus
 * that this port represents, because the island will resolve internal
 * drivers with the external driver and make the output available on
 * <label>.
 */
void compile_island_port(char*label, char*island, char*src)
{
      assert(island_table);
      vvp_island*use_island = island_table->sym_get_value(island);
      assert(use_island);
      free(island);

      vvp_net_t*net = new vvp_net_t;
      vvp_island_port*fun = new vvp_island_port(use_island);
      net->fun = fun;

	// Get the source from outside the island
      input_connect(net, 0, src);

	// Define the functor outside the island.
      define_functor_symbol(label, net);

	// Also define it inside the island.
      use_island->add_port(label, net);

      free(label);
}

void compile_island_export(char*label, char*island)
{
      fprintf(stderr, "XXXX %s .export %s;\n", label, island);
      free(label);
      free(island);
}

/*
 * This handles the compile of a .import record. A .import is an input
 * port into the island from the outside domain. For example,
 *
 *   <label> .import <island> <src> ;
 *
 * The <src> is a label in the domain outside the island, and the
 * <label> is in the domain inside the island. Branches within the
 * island use the <label>.
 */
void compile_island_import(char*label, char*island, char*src)
{
      assert(island_table);
      vvp_island*use_island = island_table->sym_get_value(island);
      assert(use_island);
      free(island);

      vvp_net_t*net = new vvp_net_t;
      vvp_island_port*fun = new vvp_island_port(use_island);
      net->fun = fun;

	// Get the source from outside the island
      input_connect(net, 0, src);

	// Define the functor only inside the island.
      use_island->add_port(label, net);

      free(label);
}

void compile_island_cleanup(void)
{
	// Call the per-island cleanup to get rid of local symbol tables.
      for (unsigned idx = 0; idx < island_count; idx += 1) {
	    island_list[idx]->compile_cleanup();
      }

	// If we are not doing valgrind checking then free the list.
#ifndef CHECK_WITH_VALGRIND
      free(island_list);
      island_list = 0;
      island_count = 0;
#endif

	// Remove the island symbol table itself.
      delete island_table;
      island_table = 0;
}

int vvp_island::robotron_inventory(FILE* out)
{
    const auto& r=robotron_islands().at(this);
    std::map<vvp_island_branch*,unsigned> branches;
    std::map<vvp_net_t*,unsigned> ports;
    for(unsigned i=0;i<r.branches.size();++i)branches[r.branches[i]]=i+1;
    for(unsigned i=0;i<r.ports.size();++i)ports[r.ports[i]]=i+1;
    if(branches_ && !branches.count(branches_))return -1;
    if(fprintf(out,"VI_ISLAND %llu %p %u %u %zu %zu\n",r.id,
               (void*)static_cast<vvp_gen_event_s*>(this),(unsigned)flagged_,
               branches_?branches.at(branches_):0,r.branches.size(),r.ports.size())<0)return -1;
    for(unsigned i=0;i<r.ports.size();++i){
        auto net=r.ports[i];auto port=dynamic_cast<vvp_island_port*>(net->fun);
        if(!port)return -1;
        if(fprintf(out,"VI_PORT %u %p %p %p\n",i+1,(void*)net,(void*)net->fun,(void*)net->fil)<0)return -1;
        if(robotron_island_vector(out,"in",port->invalue) || robotron_island_vector(out,"out",port->outvalue) ||
           robotron_island_vector(out,"scratch",port->value))return -1;
    }
    for(unsigned i=0;i<r.branches.size();++i){
        auto b=r.branches[i];
        if(!ports.count(b->a) || !ports.count(b->b) ||
           (b->next_branch && !branches.count(b->next_branch)) ||
           !branches.count(b->link[0].ptr()) || !branches.count(b->link[1].ptr()))return -1;
        if(fprintf(out,"VI_BRANCH %u %u %u %u %u %u %u %u\n",i+1,
                   b->next_branch?branches.at(b->next_branch):0,ports.at(b->a),ports.at(b->b),
                   branches.at(b->link[0].ptr()),b->link[0].port(),
                   branches.at(b->link[1].ptr()),b->link[1].port())<0)return -1;
        if(robotron_tran_inventory(out,b))return -1;
    }
    return ferror(out)?-1:0;
}
int vvp_island::robotron_flag_toggle(){flagged_=!flagged_;return 1;}
extern "C" int robotron_vvp_island_inventory(FILE* out)
{
    if(!robotron_vvp_observation_active())return -1;

    if(!out || fprintf(out,"VI_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
    // Stable lifetime order rather than allocator address order.
    std::map<unsigned long long,vvp_island*> ordered;
    for(const auto& item:robotron_islands())ordered[item.second.id]=item.first;
    for(const auto& item:ordered)if(item.second->robotron_inventory(out))return -1;
    return fprintf(out,"VI_END %zu\n",ordered.size())<0 || ferror(out)?-1:0;
}
extern "C" int robotron_vvp_island_toggle(int field)
{
    static vvp_island* owner=0;static unsigned long long lifetime=0;
    static int saved_field=-1;static vvp_vector8_t* vector=0;static vvp_vector8_t saved;
    static vvp_island_branch* branch=0;
    if(owner){
        auto found=robotron_islands().find(owner);
        if(found==robotron_islands().end() || found->second.id!=lifetime || field!=saved_field)return -1;
        if(field==0)owner->robotron_flag_toggle();
        else if(field==4){if(robotron_tran_toggle(branch)!=1)return -1;}
        else if(field==5)branch->link[0]=vvp_branch_ptr_t(branch->link[0].ptr(),branch->link[0].port()^1);
        else *vector=saved;
        owner=0;vector=0;branch=0;saved_field=-1;return 1;
    }
    if(field<0 || field>5)return -1;
    std::map<unsigned long long,vvp_island*> ordered;
    for(const auto& item:robotron_islands())ordered[item.second.id]=item.first;
    for(const auto& item:ordered){
        auto island=item.second;const auto& r=robotron_islands().at(island);
        bool changed=false;
        if(field==0){island->robotron_flag_toggle();changed=true;}
        else if(field==4 || field==5){
            for(auto b:r.branches){
                if(field==4){if(robotron_tran_toggle(b)!=1)continue;}
                else b->link[0]=vvp_branch_ptr_t(b->link[0].ptr(),b->link[0].port()^1);
                branch=b;changed=true;break;
            }
        }else{
            for(auto net:r.ports){
                auto p=dynamic_cast<vvp_island_port*>(net->fun);if(!p)return -1;
                auto v=field==2?&p->outvalue:&p->invalue;
                if(!v->size())continue;
                vector=v;saved=*v;auto b=v->value(0);
                if(field==3)v->set_bit(0,vvp_scalar_t(b.value(),b.strength0()^1,b.strength1()^1));
                else v->set_bit(0,vvp_scalar_t(b.value()==BIT4_1?BIT4_0:BIT4_1,6,6));
                changed=true;break;
            }
        }
        if(changed){owner=island;lifetime=r.id;saved_field=field;return 1;}
    }
    return 0;
}

extern "C" unsigned long long robotron_vvp_island_identity(const void* key)
{
    if(!key)return 0;
    for(const auto& item:robotron_islands())
        if(item.first->robotron_event_key()==key)return item.second.id;
    return 0;
}

extern "C" int robotron_vvp_island_filter_inventory(FILE* out)
{
    if(!robotron_vvp_observation_active())return -1;

    if(!out || fprintf(out,"VIF_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
    std::map<unsigned long long,vvp_island*> ordered;
    for(const auto& item:robotron_islands())ordered[item.second.id]=item.first;
    unsigned count=0;
    for(const auto& item:ordered){
        const auto& r=robotron_islands().at(item.second);
        for(unsigned i=0;i<r.ports.size();++i){
            auto net=r.ports[i];if(!net->fil)continue;
            auto filter=dynamic_cast<vvp_wire_vec8*>(net->fil);if(!filter)return -1;
            if(fprintf(out,"VIF_PORT %llu %u %p\n",r.id,i+1,(void*)net->fil)<0 || filter->robotron_wire_inventory(out))return -1;
            ++count;
        }
    }
    return fprintf(out,"VIF_END %u\n",count)<0 || ferror(out)?-1:0;
}
extern "C" int robotron_vvp_island_filter_toggle(int field)
{
    static vvp_wire_vec8* saved=0;static int saved_field;
    if(field<0 || field>6 || (saved && saved_field!=field))return -1;
    std::map<unsigned long long,vvp_island*> ordered;
    for(const auto& item:robotron_islands())ordered[item.second.id]=item.first;
    for(const auto& item:ordered){
        const auto& r=robotron_islands().at(item.second);
        for(auto net:r.ports){
            if(!net->fil)continue;
            auto filter=dynamic_cast<vvp_wire_vec8*>(net->fil);if(!filter)return -1;
            if(saved && filter!=saved)continue;
            int result=filter->robotron_wire_toggle(field);if(result<0)return result;
            if(result){saved=saved?0:filter;saved_field=field;return 1;}
        }
    }
    return saved?-1:0;
}

#include <typeinfo>
extern bool robotron_raw_tran_island(vvp_island*);
extern bool robotron_raw_tran_branch(vvp_island_branch*);
static int robotron_island_raw_admit()
{
    for(const auto& item:robotron_islands()){
        if(!robotron_raw_tran_island(item.first))return -1;
        for(auto b:item.second.branches)if(!robotron_raw_tran_branch(b))return -1;
        for(auto n:item.second.ports)
            if(!n->fun || typeid(*n->fun)!=typeid(vvp_island_port))return -1;
    }
    return 0;
}
static vvp_vector8_t& robotron_island_raw_vector(vvp_island_port* p,int field)
{ return field==0?p->invalue:field==1?p->outvalue:p->value; }
extern "C" int robotron_vvp_island_raw_inventory(FILE* out)
{
    if(!robotron_vvp_observation_active())return -1;

    if(!out || robotron_island_raw_admit())return -1;
    std::map<unsigned long long,vvp_island*> ordered;
    for(const auto& item:robotron_islands())ordered[item.second.id]=item.first;
    if(fprintf(out,"VIR_BEGIN 1 %llu\n",(unsigned long long)schedule_simtime())<0)return -1;
    for(const auto& item:ordered){
        const auto& r=robotron_islands().at(item.second);
        if(fprintf(out,"VIR_ISLAND %llu %p %zu\n",item.first,item.second->robotron_event_key(),r.ports.size())<0)return -1;
        for(unsigned index=0;index<r.ports.size();index++){
            auto n=r.ports[index];auto p=static_cast<vvp_island_port*>(n->fun);
            if(fprintf(out,"VIR_PORT %u %p %p %p\n",index+1,(void*)n,(void*)n->fun,(void*)n->fil)<0)return -1;
            for(int field=0;field<3;field++){
                const auto& value=robotron_island_raw_vector(p,field);
                if(fprintf(out,"VIR_VECTOR %d %u ",field,value.size())<0)return -1;
                if(!value.size() && fputc('-',out)==EOF)return -1;
                for(unsigned bit=0;bit<value.size();bit++){
                    auto scalar=value.value(bit);unsigned char raw;
                    static_assert(sizeof(scalar)==1,"Unexpected scalar representation");
                    memcpy(&raw,&scalar,1);if(fprintf(out,"%02x",raw)<0)return -1;
                }
                if(fputc('\n',out)==EOF)return -1;
            }
        }
    }
    return fprintf(out,"VIR_END %zu\n",ordered.size())<0 || ferror(out)?-1:0;
}
extern "C" int robotron_vvp_island_raw_toggle(int field,int operation)
{
    static vvp_island* owner=0;static unsigned long long lifetime;
    static vvp_vector8_t* target=0;static vvp_vector8_t saved;
    static int saved_field,saved_operation;
    if(field<0 || field>2 || operation<0 || operation>2 || robotron_island_raw_admit())return -1;
    if(owner){
        auto found=robotron_islands().find(owner);
        if(found==robotron_islands().end() || found->second.id!=lifetime || field!=saved_field || operation!=saved_operation)return -1;
        *target=saved;owner=0;target=0;return 1;
    }
    std::map<unsigned long long,vvp_island*> ordered;
    for(const auto& item:robotron_islands())ordered[item.second.id]=item.first;
    for(const auto& item:ordered)for(auto net:robotron_islands().at(item.second).ports){
        auto p=static_cast<vvp_island_port*>(net->fun);auto& value=robotron_island_raw_vector(p,field);
        unsigned index=0;unsigned char raw=0;
        if(operation!=2){
            if(!value.size())continue;
            if(operation==1){
                for(;index<value.size();index++){auto bit=value.value(index);memcpy(&raw,&bit,1);if(raw==0 || raw==136)break;}
                if(index==value.size())continue;
            }else {auto bit=value.value(0);memcpy(&raw,&bit,1);}
        }
        saved=value;target=&value;owner=item.second;lifetime=item.first;saved_field=field;saved_operation=operation;
        if(operation==2)value=vvp_vector8_t(value.size()+1);
        else {raw=operation==1?raw^136:raw==238?102:238;vvp_scalar_t bit;memcpy(&bit,&raw,1);value.set_bit(index,bit);}
        return 1;
    }
    return 0;
}

#include <sstream>
#include <string>

// Scan all fields; encode each island independently against an immutable reference.
static std::map<unsigned long long,std::string> robotron_island_raw_reference_rows;
static bool robotron_island_raw_reference_ready;
static int robotron_island_raw_rows(std::map<unsigned long long,std::string>& rows)
{
    char* data=0;size_t size=0;FILE* stream=open_memstream(&data,&size);
    if(!stream)return -1;
    int result=robotron_vvp_island_raw_inventory(stream);
    if(fclose(stream))result=-1;
    if(result){free(data);return -1;}
    std::string text(data,size);free(data);std::istringstream input(text);std::string line;
    if(!std::getline(input,line) || line.compare(0,10,"VIR_BEGIN "))return -1;
    unsigned long long id=0;
    while(std::getline(input,line)){
        if(line.compare(0,11,"VIR_ISLAND ")==0){
            std::istringstream row(line);std::string marker;row>>marker>>id;
            if(!id || rows.count(id))return -1;
            rows[id]=line+"\n";
        }else if((line.compare(0,9,"VIR_PORT ")==0 || line.compare(0,11,"VIR_VECTOR ")==0)){
            if(!id)return -1;rows[id]+=line+"\n";
        }else if(line=="VIR_END "+std::to_string(rows.size())){
            return std::getline(input,line)?-1:0;
        }else return -1;
    }
    return -1;
}
static int robotron_island_raw_row(FILE* out,unsigned long long id,const std::string& row,const std::string& reference)
{
    size_t prefix=0,suffix=0;
    while(prefix<row.size() && prefix<reference.size() && row[prefix]==reference[prefix])prefix++;
    while(suffix<row.size()-prefix && suffix<reference.size()-prefix && row[row.size()-1-suffix]==reference[reference.size()-1-suffix])suffix++;
    if(fprintf(out,"VIX_ROW %llu %zu %zu ",id,prefix,suffix)<0)return -1;
    static const char digits[]="0123456789abcdef";
    if(prefix+suffix==row.size()){if(fputc('-',out)==EOF)return -1;}
    else for(size_t i=prefix;i<row.size()-suffix;i++){
        unsigned char c=row[i];if(fputc(digits[c>>4],out)==EOF || fputc(digits[c&15],out)==EOF)return -1;
    }
    return fputc('\n',out)==EOF?-1:0;
}
extern "C" int robotron_vvp_island_raw_reference(FILE* out)
{
    if(!out || robotron_island_raw_reference_ready)return -1;
    std::map<unsigned long long,std::string> rows;
    if(robotron_island_raw_rows(rows))return -1;
    if(fprintf(out,"VIX_BEGIN R %llu %zu %zu\n",(unsigned long long)schedule_simtime(),rows.size(),rows.size())<0)return -1;
    for(auto row:rows)if(robotron_island_raw_row(out,row.first,row.second,""))return -1;
    if(fprintf(out,"VIX_END %zu\n",rows.size())<0 || ferror(out))return -1;
    robotron_island_raw_reference_rows=rows;robotron_island_raw_reference_ready=true;return 0;
}
extern "C" int robotron_vvp_island_raw_delta_inventory(FILE* out)
{
    if(!robotron_vvp_observation_active())return -1;

    if(!out || !robotron_island_raw_reference_ready)return -1;
    std::map<unsigned long long,std::string> rows;
    if(robotron_island_raw_rows(rows))return -1;
    for(auto row:robotron_island_raw_reference_rows)if(!rows.count(row.first))return -1;
    size_t changed=0;
    for(auto row:rows){auto old=robotron_island_raw_reference_rows.find(row.first);if(old==robotron_island_raw_reference_rows.end() || old->second!=row.second)changed++;}
    if(fprintf(out,"VIX_BEGIN D %llu %zu %zu\n",(unsigned long long)schedule_simtime(),rows.size(),changed)<0)return -1;
    for(auto row:rows){
        auto old=robotron_island_raw_reference_rows.find(row.first);
        if(old==robotron_island_raw_reference_rows.end() || old->second!=row.second)
            if(robotron_island_raw_row(out,row.first,row.second,old==robotron_island_raw_reference_rows.end()?"":old->second))return -1;
    }
    return fprintf(out,"VIX_END %zu\n",changed)<0 || ferror(out)?-1:0;
}
