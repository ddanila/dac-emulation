#include "cpu_bus_steps.h"
/* Experimental I/O-only half-cycle adapter over the generated C core.
 * One rising call per T-state; every rising call must have a falling call.
 * Supply live bus data before the falling call. Reset cancels pending work.
 * Non-I/O behavior retains the original whole-cycle model. */
#include "candidate.h"
typedef struct { k7658_z80_t cpu; uint64_t pins; int pending,fetch_ready; } c_read_half;
static inline int c_read_consuming(unsigned step) {
 switch(step){case 974:case 1188:case 1222:case 1256:case 1285:case 1314:case 1352:case 1390:case 1418:case 1463:case 1495:case 1537:case 1589:return 1;default:return 0;}
}
static inline int c_read_waiting(unsigned step) {
 switch(step){case 973:case 1187:case 1221:case 1255:case 1284:case 1313:case 1351:case 1389:case 1417:case 1462:case 1494:case 1536:case 1588:return 1;default:return 0;}
}
static inline int c_write_waiting(unsigned step) {switch(step){case 923:case 1191:case 1225:case 1259:case 1288:case 1317:case 1355:case 1393:case 1421:case 1473:case 1505:case 1552:case 1604:return 1;default:return 0;}}
static inline int memory_consuming(unsigned step) {switch(step){case 513:case 516:case 524:case 534:case 539:case 543:case 551:case 554:case 562:case 565:case 580:case 585:case 588:case 596:case 599:case 602:case 605:case 616:case 619:case 634:case 637:case 640:case 643:case 648:case 651:case 659:case 662:case 665:case 668:case 676:case 683:case 690:case 696:case 711:case 714:case 717:case 722:case 725:case 728:case 731:case 734:case 737:case 740:case 764:case 767:case 770:case 773:case 776:case 779:case 782:case 785:case 788:case 792:case 795:case 798:case 801:case 804:case 807:case 810:case 813:case 816:case 819:case 836:case 847:case 850:case 853:case 856:case 859:case 862:case 865:case 868:case 878:case 881:case 891:case 902:case 905:case 908:case 911:case 914:case 917:case 920:case 927:case 930:case 947:case 958:case 961:case 964:case 967:case 970:case 977:case 980:case 990:case 1001:case 1004:case 1007:case 1010:case 1013:case 1016:case 1019:case 1022:case 1034:case 1037:case 1054:case 1065:case 1068:case 1071:case 1074:case 1077:case 1080:case 1090:case 1101:case 1104:case 1107:case 1110:case 1113:case 1116:case 1119:case 1122:case 1139:case 1150:case 1153:case 1158:case 1161:case 1164:case 1167:case 1177:case 1202:case 1205:case 1214:case 1217:case 1236:case 1239:case 1242:case 1245:case 1248:case 1251:case 1270:case 1273:case 1299:case 1302:case 1305:case 1308:case 1328:case 1331:case 1341:case 1366:case 1369:case 1372:case 1375:case 1379:case 1404:case 1407:case 1432:case 1435:case 1438:case 1441:case 1445:case 1453:case 1470:case 1477:case 1485:case 1502:case 1509:case 1522:case 1549:case 1561:case 1574:case 1601:case 1615:case 1622:case 1625:case 1630:case 1669:case 1672:case Z80_DDFD_D_T3:case Z80_DDFD_D_T6:return 1;default:return 0;}}
static inline int memory_waiting(unsigned step) {switch(step){case 512:case 515:case 518:case 523:case 533:case 538:case 542:case 550:case 553:case 556:case 561:case 564:case 579:case 584:case 587:case 595:case 598:case 601:case 604:case 607:case 610:case 615:case 618:case 633:case 636:case 639:case 642:case 647:case 650:case 658:case 661:case 664:case 667:case 670:case 675:case 679:case 682:case 686:case 689:case 692:case 695:case 710:case 713:case 716:case 721:case 724:case 727:case 730:case 733:case 736:case 739:case 742:case 745:case 748:case 751:case 754:case 757:case 760:case 763:case 766:case 769:case 772:case 775:case 778:case 781:case 784:case 787:case 791:case 794:case 797:case 800:case 803:case 806:case 809:case 812:case 815:case 818:case 822:case 825:case 829:case 832:case 835:case 839:case 842:case 846:case 849:case 852:case 855:case 858:case 861:case 864:case 867:case 871:case 874:case 877:case 880:case 884:case 887:case 890:case 894:case 897:case 901:case 904:case 907:case 910:case 913:case 916:case 919:case 926:case 929:case 933:case 936:case 940:case 943:case 946:case 950:case 953:case 957:case 960:case 963:case 966:case 969:case 976:case 979:case 983:case 986:case 989:case 993:case 996:case 1000:case 1003:case 1006:case 1009:case 1012:case 1015:case 1018:case 1021:case 1025:case 1028:case 1033:case 1036:case 1040:case 1043:case 1047:case 1050:case 1053:case 1057:case 1060:case 1064:case 1067:case 1070:case 1073:case 1076:case 1079:case 1083:case 1086:case 1089:case 1093:case 1096:case 1100:case 1103:case 1106:case 1109:case 1112:case 1115:case 1118:case 1121:case 1125:case 1128:case 1132:case 1135:case 1138:case 1142:case 1145:case 1149:case 1152:case 1157:case 1160:case 1163:case 1166:case 1170:case 1173:case 1176:case 1180:case 1183:case 1201:case 1204:case 1207:case 1210:case 1213:case 1216:case 1235:case 1238:case 1241:case 1244:case 1247:case 1250:case 1269:case 1272:case 1275:case 1278:case 1298:case 1301:case 1304:case 1307:case 1327:case 1330:case 1333:case 1336:case 1340:case 1347:case 1365:case 1368:case 1371:case 1374:case 1378:case 1385:case 1403:case 1406:case 1409:case 1412:case 1431:case 1434:case 1437:case 1440:case 1444:case 1447:case 1452:case 1465:case 1469:case 1476:case 1479:case 1484:case 1497:case 1501:case 1508:case 1511:case 1521:case 1539:case 1548:case 1560:case 1563:case 1573:case 1591:case 1600:case 1614:case 1618:case 1621:case 1624:case 1629:case 1633:case 1649:case 1652:case 1662:case 1665:case 1668:case 1671:case 1679:case 1682:case Z80_DDFD_D_T2:case Z80_DDFD_D_T5:case Z80_DDFD_LDHLN_WR_T2:return 1;default:return 0;}}
static inline int fetch_waiting(unsigned step) {switch(step){case Z80_M1_T2:case Z80_DDFD_M1_T2:case Z80_CB_M1_T2:case Z80_ED_M1_T2:case 1638:case 1644:case 1657:return 1;default:return 0;}}
static inline void c_read_reset(c_read_half *c) {
 c->pins=k7658_z80_init(&c->cpu);c->pending=0;c->fetch_ready=0;
}
static inline uint64_t c_read_rise(c_read_half *c,uint64_t pins) {
 if(c->fetch_ready){uint64_t wait=pins&Z80_WAIT;pins=k7658_z80_tick(&c->cpu,pins&~Z80_WAIT)|wait;c->fetch_ready=0;}
 c->pending=fetch_waiting(c->cpu.step)?7:memory_consuming(c->cpu.step)?5:(memory_waiting(c->cpu.step)?6:(c_write_waiting(c->cpu.step)?3:(((pins&(Z80_IORQ|Z80_WR))==(Z80_IORQ|Z80_WR))?4:(c_read_consuming(c->cpu.step)?1:(c_read_waiting(c->cpu.step)?2:0)))));
 c->pins=c->pending?pins:k7658_z80_tick(&c->cpu,pins);
 return c->pins;
}
static inline uint64_t c_read_fall(c_read_half *c,uint64_t pins) {
 if(c->pending==7){c->fetch_ready=!(pins&Z80_WAIT);c->pending=0;return c->pins=pins;}
 if(c->pending){
  uint64_t selected=pins&(UINT64_C(0xffffff)|Z80_IORQ|Z80_WR);
  c->pins=k7658_z80_tick(&c->cpu,pins);
  if(c->pending==3)c->pins=(c->pins&~(UINT64_C(0xffffff)|Z80_IORQ|Z80_WR))|selected;
  if(c->pending==4){c->pins&=~(Z80_IORQ|Z80_WR);}
  // Release after sampling at T3 falling; internal register changes precede
  // the next rising-edge machine cycle. No instruction T-state is added.
  if(c->pending==1)c->pins&=~(Z80_IORQ|Z80_RD);
  c->pending=0;
 }else c->pins=pins;
 return c->pins;
}
