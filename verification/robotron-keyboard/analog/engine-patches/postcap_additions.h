/* Experimental recovery of additions after capacitor loading. Device conductances,
 * switch decisions and histories remain unchanged binary64 values. */
#ifndef ROBOTRON_POSTCAP_ADDITIONS_H
#define ROBOTRON_POSTCAP_ADDITIONS_H
int RobotronPostCapEnabled(void)
{
    static int mode=-1;
    if(mode==-1) {
        const char *v=getenv("ROBOTRON_POSTCAP_ASSEMBLY");
        mode=(!v || !strcmp(v,"off"))?0:!strcmp(v,"exact")?1:-2;
        if(mode==1) {
            const char *cap=getenv("ROBOTRON_CAP_ASSEMBLY");
            if(!cap || strcmp(cap,"exact"))mode=-2;
        }
        fprintf(stderr,"POSTCAP_ASSEMBLY mode=%d\n",mode);
    }
    return mode;
}
int RobotronPostCapAdd(int p,int n,double conductance,const double *before,const double *after)
{
    int result=0;mpq_t g;
    if(p==n || p<0 || n<0 || conductance<0 || !isfinite(conductance))return 1;
    mpq_init(g);mpq_set_d(g,conductance);
    result|=robotron_cap_entry(p,p,g,1,before[0],after[0]);
    result|=robotron_cap_entry(n,n,g,1,before[1],after[1]);
    result|=robotron_cap_entry(p,n,g,-1,before[2],after[2]);
    result|=robotron_cap_entry(n,p,g,-1,before[3],after[3]);
    mpq_clear(g);return result;
}
#endif
