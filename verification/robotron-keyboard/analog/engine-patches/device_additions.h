/* Diagnostic preservation of BJT/diode additions. Nonlinear evaluation and
 * individual contributions remain binary64; only accumulation is corrected. */
#ifndef ROBOTRON_DEVICE_ADDITIONS_H
#define ROBOTRON_DEVICE_ADDITIONS_H
typedef struct { double *pointer; int row, col; } RobotronDeviceAddress;
static RobotronDeviceAddress device_addresses[4096];
static int device_address_count, device_error;
static double *device_ground;
int RobotronDeviceEnabled(void)
{
    static int mode=-1;
    if(mode==-1) {
        const char *v=getenv("ROBOTRON_DEVICE_ASSEMBLY");
        mode=(!v || !strcmp(v,"off"))?0:!strcmp(v,"exact")?1:-2;
        if(mode==1) {
            const char *cap=getenv("ROBOTRON_CAP_ASSEMBLY");
            if(!cap || strcmp(cap,"exact"))mode=-2;
        }
        fprintf(stderr,"DEVICE_ASSEMBLY mode=%d\n",mode);
    }
    return mode;
}
static double *robotron_device_address(double *pointer,int row,int col)
{
    if(RobotronDeviceEnabled()!=1 || !pointer)return pointer;
    if(!row || !col) { device_ground=pointer;return pointer; }
    for(int i=0;i<device_address_count;i++) {
        if(device_addresses[i].pointer==pointer) {
            if(device_addresses[i].row!=row || device_addresses[i].col!=col)device_error=1;
            return pointer;
        }
    }
    if(device_address_count==4096) { device_error=1;return pointer; }
    device_addresses[device_address_count++]=(RobotronDeviceAddress){pointer,row,col};
    return pointer;
}
double RobotronDeviceAdd(double *pointer,double value,int rhs_row)
{
    double before=*pointer;
    *pointer+=value;
    int mode=RobotronDeviceEnabled(),row=rhs_row,col=-1;
    if(mode==0)return *pointer;
    if(mode!=1 || !isfinite(value)) { device_error=1;return *pointer; }
    if(rhs_row<0) {
        row=col=0;
        for(int i=0;i<device_address_count;i++)if(device_addresses[i].pointer==pointer) {
            row=device_addresses[i].row;col=device_addresses[i].col;break;
        }
        /* The sparse ground trash entry is intentionally unregistered. */
        if(!row) { if(pointer!=device_ground)device_error=1;return *pointer; }
    }
    mpq_t exact;mpq_init(exact);mpq_set_d(exact,value);
    device_error|=robotron_cap_entry(row,col,exact,1,before,*pointer);
    mpq_clear(exact);
    return *pointer;
}
#endif
