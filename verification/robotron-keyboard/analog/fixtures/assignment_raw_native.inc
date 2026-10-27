/* Test adapter compiled into both original and candidate schedule.cc. Production
 * observers never call these factories. Native queue insertion, RTTI, dispatch
 * and deletion remain in the runtime under test. */
class robotron_assignment_private : public assign_vector8_event_s {
    bool invert_;
    bool bypass_;
public:
    explicit robotron_assignment_private(int family):invert_(family==2),bypass_(family==3){}
    static void* operator new(size_t size){return ::operator new(size);}
    static void operator delete(void* p){::operator delete(p);}
    void run_run() override {
        if(invert_ && val.size()) {
            auto scalar=val.value(0);unsigned char raw;memcpy(&raw,&scalar,1);
            raw^=0x88;memcpy(&scalar,&raw,1);val.set_bit(0,scalar);
        }
        printf("AF_PRIVATE %d\n",invert_);
        if(bypass_)vvp_send_vec8(ptr,val);
        else assign_vector8_event_s::run_run();
    }
};
extern "C" void robotron_assignment_fixture(vvp_net_t* target,unsigned port,unsigned width,unsigned char byte,int family,int insertion)
{
    assign_vector8_event_s* event;
    if(family)event=new robotron_assignment_private(family);
    else event=new assign_vector8_event_s;
    event->ptr=vvp_net_ptr_t(target,port);
    event->val=vvp_vector8_t(width);vvp_scalar_t scalar;memcpy(&scalar,&byte,1);
    for(unsigned i=0;i<width;i++)event->val.set_bit(i,scalar);
    if(insertion==0)schedule_init_event(event);
    else if(insertion==1)schedule_event_(event,0,SEQ_ACTIVE);
    else {event->run_run();delete event;}
}
