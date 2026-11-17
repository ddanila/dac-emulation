// Numerical counterpart of trajectory.py. Reduced fields, no tube calibration.
// Double precision RK4; do not compile with fast-math.
#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
using State=std::array<double,6>;
constexpr double E=1.602176634e-19, M=9.1093837139e-31, C=299792458.;
constexpr double REST=M*C*C/E;
enum { SCREEN_Z,RADIUS,WIDTH,HEIGHT,GUN,NECK,YOKE_START,YOKE_LENGTH,
       H_TESLA,V_TESLA,INITIAL_EV,SOURCE_RADIUS,DIVERGENCE,G2_LENGTH,
       FOCUS_START,FOCUS_LENGTH,ANODE_START,ANODE_LENGTH };
static std::array<double,4> smooth(double z,double begin,double length) {
    double s=(z-begin)/length;
    if(s<=0)return {0,0,0,0}; if(s>=1)return {1,0,0,0};
    return {6*std::pow(s,5)-15*std::pow(s,4)+10*std::pow(s,3),
        (30*std::pow(s,4)-60*std::pow(s,3)+30*s*s)/length,
        (120*std::pow(s,3)-180*s*s+60*s)/(length*length),
        (360*s*s-360*s+60)/(length*length*length)};
}
static std::array<double,4> potential(double x,double y,double z,const double* e,const double* p) {
    std::array<double,4> v{};
    const double amplitude[]={e[1],e[2]-e[1],e[0]-e[2]};
    const double begin[]={0,p[FOCUS_START],p[ANODE_START]};
    const double length[]={p[G2_LENGTH],p[FOCUS_LENGTH],p[ANODE_LENGTH]};
    for(int j=0;j<3;++j) {auto a=smooth(z,begin[j],length[j]);for(int i=0;i<4;++i)v[i]+=amplitude[j]*a[i];}
    double r2=x*x+y*y;
    return {v[0]-r2*v[2]/4,-x*v[2]/2,-y*v[2]/2,v[1]-r2*v[3]/4};
}
static State rhs(double z,const State& s,const double* e,const double* p) {
    double x=s[0],y=s[1],ux=s[2],uy=s[3],uz=s[4];
    if(uz<=1e-9)throw std::runtime_error("reversed");
    double gamma=std::sqrt(1+ux*ux+uy*uy+uz*uz);
    auto g=potential(x,y,z,e,p);
    double q=(z-p[YOKE_START])/p[YOKE_LENGTH];
    double env=(q>0&&q<1)?2*std::pow(std::sin(std::acos(-1.)*q),2):0;
    double bx=-e[4]*p[V_TESLA]*env,by=e[3]*p[H_TESLA]*env;
    double electric=E/(M*C*C)*gamma/uz,magnetic=E/(M*C)/uz;
    return {ux/uz,uy/uz,electric*g[1]+magnetic*uz*by,
        electric*g[2]-magnetic*uz*bx,electric*g[3]-magnetic*(ux*by-uy*bx),gamma/(C*uz)};
}
static State add(const State& s,const State& k,double h) {
    State r;for(int i=0;i<6;++i)r[i]=s[i]+h*k[i];return r;
}
static double surface(const State& s,const double* p) {
    double r=s[0]*s[0]+s[1]*s[1];
    return r>=p[RADIUS]*p[RADIUS]?-INFINITY:p[SCREEN_Z]-p[RADIUS]+std::sqrt(p[RADIUS]*p[RADIUS]-r);
}
// e: anode, g2, focus, Ih, Iv, origin x/y, slope x/y, spatial step.
// out: flight seconds, max energy error eV, impact eV, x/y; reason returned.
// reasons: low acceleration, reversed, gun, neck, screen, clipping, budget.
extern "C" int crt_ray(const double* e,const double* p,double* out,double* points,int capacity,int* count) {
    *count=0;for(int i=0;i<5;++i)out[i]=0;
    if(e[0]<=100)return 0;
    double gamma=1+p[INITIAL_EV]/REST,u=std::sqrt((gamma-1)*(gamma+1));
    double uz=u/std::sqrt(1+e[7]*e[7]+e[8]*e[8]);
    State s={e[5],e[6],e[7]*uz,e[8]*uz,uz,0};
    double energy0=p[INITIAL_EV]-potential(e[5],e[6],0,e,p)[0];
    double z=0,maxerr=0;int reason=6;
    auto point=[&]() {if(*count>=capacity)return false;int i=3*(*count)++;points[i]=z;points[i+1]=s[0];points[i+2]=s[1];return true;};
    if(!point())return -1;
    for(int index=0;index<int(std::ceil(p[SCREEN_Z]/e[9]))+2;++index) {
        State old=s;double previous=z,h=std::min(e[9],p[SCREEN_Z]-z);
        try {
            auto a=rhs(z,old,e,p);auto b=rhs(z+h/2,add(old,a,h/2),e,p);
            auto c=rhs(z+h/2,add(old,b,h/2),e,p);auto d=rhs(z+h,add(old,c,h),e,p);
            for(int i=0;i<6;++i)s[i]=old[i]+h*(a[i]+2*b[i]+2*c[i]+d[i])/6;
        } catch(const std::runtime_error&) {reason=1;break;}
        z+=h;for(double v:s)if(!std::isfinite(v))return -2;
        double k=REST*(std::sqrt(1+s[2]*s[2]+s[3]*s[3]+s[4]*s[4])-1);
        maxerr=std::max(maxerr,std::abs(k-potential(s[0],s[1],z,e,p)[0]-energy0));
        if(s[4]<=0){reason=1;break;}
        double gun_end=p[ANODE_START]+p[ANODE_LENGTH];
        if(z<gun_end&&std::hypot(s[0],s[1])>p[GUN]){reason=2;break;}
        if(gun_end<=z&&z<p[YOKE_START]+p[YOKE_LENGTH]&&std::hypot(s[0],s[1])>p[NECK]){reason=3;break;}
        if(z>=surface(s,p)) {
            double lo=0,hi=1;
            for(int n=0;n<32;++n){double t=(lo+hi)/2;State test;for(int i=0;i<6;++i)test[i]=old[i]+t*(s[i]-old[i]);
                if(previous+t*h>=surface(test,p))hi=t;else lo=t;}
            double t=(lo+hi)/2;for(int i=0;i<6;++i)s[i]=old[i]+t*(s[i]-old[i]);z=previous+t*h;
            reason=(std::abs(s[0])<=p[WIDTH]/2&&std::abs(s[1])<=p[HEIGHT]/2)?4:5;break;
        }
        if(index%5==0&&!point())return -1;
    }
    if(!point())return -1;
    out[0]=s[5];out[1]=maxerr;out[2]=REST*(std::sqrt(1+s[2]*s[2]+s[3]*s[3]+s[4]*s[4])-1);
    out[3]=s[0];out[4]=s[1];return reason;
}
