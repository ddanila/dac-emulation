/* Compile the upstream evaluator with minimal ABI stubs; exercise cache lifetime
 * and observable effects independently of ngspice circuit convergence. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#define OK 0
#define E_PARMVAL 1
#define E_PANIC 2
#define EXIT_BAD 1
#undef HUGE
#define HUGE HUGE_VAL
#define CONSTCtoK 273.15
#define PTbinary(f) ((double(*)(double,double))(f))
#define PTunary(f) ((double(*)(double))(f))
#define PTunary_with_private(f) ((double(*)(double,void*))(f))
enum {PT_CONSTANT,PT_VAR,PT_FUNCTION,PT_TERN,PT_PLUS,PT_MINUS,PT_TIMES,PT_DIVIDE,PT_POWER,PT_TIME,PT_TEMPERATURE,PT_FREQUENCY};
enum {PTF_POW,PTF_PWR,PTF_MIN,PTF_MAX,PTF_DDT,PTF_OTHER};
typedef struct node {int type,usecnt,funcnum,valueIndex; double constant; void *data; void (*function)(void); char *funcname; struct node *left,*right;} INPparseNode;
typedef struct {int numVars;} IFparseTree;
typedef struct {IFparseTree p; INPparseNode *tree,**derivs;} INPparseTree;
typedef struct {double CKTtime,CKTtemp,CKTomega;} CKTcircuit;
double PTfudge_factor; int ft_ngdebug=0,ft_stricterror=0;
void controlled_exit(int n){exit(n);}
void INPptPrint(const char *s,void *p){(void)s;(void)p;}
/* EVALUATOR */
static int calls;
static double add(double a,double b){++calls;return a+b;}
static double state(double a,void *p){return a+ ++*(int*)p;}
static double bad(double a){(void)a;return HUGE;}
int main(int argc,char **argv){
 assert(argc==2);setenv("ROBOTRON_EVAL_CACHE",argv[1],1);
 INPparseNode x={.type=PT_VAR},y={.type=PT_VAR,.valueIndex=1};
 INPparseNode sum={.type=PT_PLUS,.usecnt=3,.left=&x,.right=&y,.function=(void(*)(void))add,.funcname="add"};
 INPparseNode twice={.type=PT_PLUS,.left=&sum,.right=&sum,.function=(void(*)(void))add,.funcname="add"};
 INPparseNode *derivs[]={&sum,&sum}; INPparseTree tree={{2},&twice,derivs};
 double vals[]={1.25,-0.75},out,d[2];
 for(int i=0;i<100;i++){
  vals[0]+=0.125;calls=0;
  assert(IFeval((IFparseTree*)&tree,1e-12,&out,vals,d)==OK);
  double expected=vals[0]+vals[1];assert(out==expected+expected && d[0]==expected && d[1]==expected);
  assert(calls==(!strcmp(argv[1],"exact")?2:5));
 }
 int counter=0;
 INPparseNode impure={.type=PT_FUNCTION,.usecnt=3,.left=&x,.data=&counter,.funcnum=PTF_OTHER,.function=(void(*)(void))state};
 sum.left=&impure; tree.p.numVars=0;calls=0;
 assert(IFeval((IFparseTree*)&tree,1e-9,&out,vals,d)==OK);assert(counter==2);
 /* A cached parent must not suppress the second private function call. */
 assert(out==(vals[0]+1+vals[1])+(vals[0]+2+vals[1]));
 INPparseNode error={.type=PT_FUNCTION,.usecnt=2,.left=&x,.funcnum=PTF_OTHER,.function=(void(*)(void))bad,.funcname="bad"};
 tree.tree=&error;assert(IFeval((IFparseTree*)&tree,1e-12,&out,vals,d)==E_PARMVAL);
 INPparseNode pair={.left=&x,.right=&error},tern={.type=PT_TERN,.usecnt=2,.left=&x,.right=&pair};
 tree.tree=&tern;assert(IFeval((IFparseTree*)&tree,1e-12,&out,vals,d)==OK);assert(out==vals[0]);
 CKTcircuit ckt={1,300,2*M_PI};INPparseNode clock={.type=PT_TIME,.usecnt=2,.data=&ckt};tree.tree=&clock;
 for(int i=0;i<10;i++){ckt.CKTtime=i;assert(IFeval((IFparseTree*)&tree,1e-12,&out,vals,d)==OK);assert(out==i);}
 puts("Evaluator value/gradient, lifetime, private state, errors and short-circuit checks pass");
}
