#include "memoria_mobile.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr,"CHECK failed: %s:%d: %s\n",__FILE__,__LINE__,#x); return 1; } } while(0)

static memoria_mobile_status store(memoria_mobile_handle *h, int i, memoria_mobile_buffer *out) {
    char json[768];
    snprintf(json,sizeof(json),"{\"episode_id\":\"prod-%d\",\"session_id\":\"production-upgrade\",\"role\":\"user\",\"text\":\"production episode %d\",\"event_type\":\"upgrade-test\",\"topics_csv\":\"production,upgrade\",\"order\":%d}",i,i,i);
    memoria_mobile_buffer in={(const uint8_t*)json,strlen(json)};
    return memoria_mobile_store_episode_json(h,in,out);
}
static int contains(memoria_mobile_buffer b,const char *s){return b.data && strstr((const char*)b.data,s)!=NULL;}
static int count_is(memoria_mobile_handle *h,int n){
    char req[128],needle[64]; memoria_mobile_buffer out={0};
    snprintf(req,sizeof(req),"{\"episode_offset\":0,\"episode_limit\":1}");
    memoria_mobile_buffer in={(const uint8_t*)req,strlen(req)};
    if(memoria_mobile_export_snapshot_json(h,in,&out)!=MEMORIA_MOBILE_OK) return 0;
    snprintf(needle,sizeof(needle),"\"episodes\":%d",n);
    int ok=contains(out,needle); if(!ok) fprintf(stderr,"snapshot=%s\n",out.data?(const char*)out.data:"NULL");
    memoria_mobile_free_buffer(out); return ok;
}
static int recall_id(memoria_mobile_handle *h,int i,int expect){
    char req[512],needle[64]; memoria_mobile_buffer out={0};
    snprintf(req,sizeof(req),"{\"query\":\"production episode %d\",\"session_id\":\"production-upgrade\",\"event_type\":\"upgrade-test\",\"topics_csv\":\"production,upgrade\"}",i);
    memoria_mobile_buffer in={(const uint8_t*)req,strlen(req)};
    memoria_mobile_status st=memoria_mobile_recall_episode_json(h,in,&out);
    snprintf(needle,sizeof(needle),"prod-%d",i);
    int found=(st==MEMORIA_MOBILE_OK && contains(out,needle));
    if(out.data) memoria_mobile_free_buffer(out);
    return expect?found:!found;
}
int main(int argc,char **argv){
    CHECK(argc==5); const char *mode=argv[1],*dir=argv[2],*org=argv[3]; int target=atoi(argv[4]);
    memoria_mobile_handle *h=NULL; memoria_mobile_buffer out={0};
    CHECK(memoria_mobile_open(dir,org,&h)==MEMORIA_MOBILE_OK);
    if(strcmp(mode,"seed")==0){
        for(int i=1;i<=target;i++){ CHECK(store(h,i,&out)==MEMORIA_MOBILE_OK); CHECK(contains(out,"\"durable\":true")); memoria_mobile_free_buffer(out); out=(memoria_mobile_buffer){0}; }
        CHECK(memoria_mobile_flush(h)==MEMORIA_MOBILE_OK); CHECK(count_is(h,target)); CHECK(recall_id(h,target,1));
    } else if(strcmp(mode,"extend")==0){
        CHECK(count_is(h,256)); CHECK(recall_id(h,1,1)); CHECK(recall_id(h,256,1));
        for(int i=257;i<=target;i++){ CHECK(store(h,i,&out)==MEMORIA_MOBILE_OK); memoria_mobile_free_buffer(out); out=(memoria_mobile_buffer){0}; }
        CHECK(memoria_mobile_flush(h)==MEMORIA_MOBILE_OK); CHECK(count_is(h,target)); CHECK(recall_id(h,target,1)); CHECK(recall_id(h,1,1));
    } else if(strcmp(mode,"verify")==0){
        CHECK(count_is(h,target)); CHECK(recall_id(h,1,1)); CHECK(recall_id(h,target,1)); if(target==256) CHECK(recall_id(h,257,0));
    } else { fprintf(stderr,"unknown mode\n"); memoria_mobile_close(h); return 2; }
    memoria_mobile_close(h); printf("%s OK count=%d\n",mode,target); return 0;
}
