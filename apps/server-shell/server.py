"""Unified local entry point for Memoria Admin and BDR Explorer."""
from __future__ import annotations
import argparse, json, mimetypes, socket
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from auth import AuthManager
from autonomous_tests import AutonomousTestManager
from config import ShellConfig
from device_registry import AUDIT_PATH, IDENTITY_PATH, AuditLog, DeviceRegistry, ServerIdentity
from device_auth import DeviceAuthManager, DeviceAuthority
from guided_curiosity import TrajectoryGuidedCuriosityEngine
from epistemic_feedback import EpistemicFeedback
from epistemic_trajectory import EpistemicTrajectoryStore
from growth_diagnostics import GrowthDiagnostics
from knowledge_bdr import KnowledgeBDR
from learning_worker import LearningWorker
from server_knowledge import ServerKnowledge
from site_ingest import SiteIngestManager
APPS_DIR=Path(__file__).resolve().parents[1]; SHELL_STATIC=Path(__file__).with_name("static"); MEMORIA_STATIC=APPS_DIR/"memoria-admin"/"static"; BDR_STATIC=APPS_DIR/"bdr-explorer"/"explorer"/"static"
HOP_BY_HOP_HEADERS={"connection","keep-alive","proxy-authenticate","proxy-authorization","te","trailers","transfer-encoding","upgrade"}
def proxy_target(c,path):
    p="/api/server/v1/models"
    if path==p:return c.model_gateway_url,"/admin/models"
    if path.startswith(p+"/"):return c.model_gateway_url,"/admin/models/"+path[len(p)+1:]
    if path=="/api/v1" or path.startswith("/api/v1/"):return c.memoria_api_url,path
    p="/api/bdr-explorer/v1"
    if path==p:return c.bdr_explorer_url,"/api"
    if path.startswith(p+"/"):return c.bdr_explorer_url,"/api/"+path[len(p)+1:]
    return None
def static_target(path):
    r={
        "/":SHELL_STATIC/"index.html","/index.html":SHELL_STATIC/"index.html",
        "/shell.css":SHELL_STATIC/"shell.css","/shell.js":SHELL_STATIC/"shell.js",
        "/login":SHELL_STATIC/"login.html","/login.css":SHELL_STATIC/"login.css","/login.js":SHELL_STATIC/"login.js",
        "/devices":SHELL_STATIC/"devices.html","/devices/":SHELL_STATIC/"devices.html","/devices.js":SHELL_STATIC/"devices.js",
        "/admin/memoria":MEMORIA_STATIC/"index.html","/admin/memoria/":MEMORIA_STATIC/"index.html",
        "/admin/memoria/style.css":MEMORIA_STATIC/"style.css","/admin/memoria/app.js":MEMORIA_STATIC/"app.js",
        "/admin/memoria/history-fix.js":MEMORIA_STATIC/"history-fix.js",
        "/admin/memoria/curiosity-admin.js":MEMORIA_STATIC/"curiosity-admin.js",
        "/admin/memoria/growth-diagnostics.js":MEMORIA_STATIC/"growth-diagnostics.js",
        "/admin/memoria/diagnostics-fix.js":MEMORIA_STATIC/"diagnostics-fix.js",
        "/explorer/bdr":BDR_STATIC/"index.html","/explorer/bdr/":BDR_STATIC/"index.html",
        "/explorer/bdr/styles.css":BDR_STATIC/"styles.css","/explorer/bdr/app.js":BDR_STATIC/"app.js",
    }
    return r.get(path)

def server_capabilities():
    return {
        "schema":"memoria-server-capabilities/v1",
        "device_registry_v1":True,
        "device_heartbeat_v1":True,
        "device_auth_v1":True,
        "device_certificates_v1":True,
        "audit_log_v1":True,
        "server_identity_v1":True,
        "explorer_temporal_v1":True,
        "format_bdr":False,
    }
class ShellHandler(BaseHTTPRequestHandler):
    config=ShellConfig(); auth:AuthManager; autotests:AutonomousTestManager; curiosity:TrajectoryGuidedCuriosityEngine; knowledge:ServerKnowledge; site_ingest:SiteIngestManager; growth:GrowthDiagnostics; trajectories:EpistemicTrajectoryStore; identity:ServerIdentity; audit:AuditLog; devices:DeviceRegistry; device_authority:DeviceAuthority; device_auth:DeviceAuthManager
    episode_write_lock=Lock()
    def _session_token(self):
        raw=self.headers.get("Cookie")
        if not raw:return None
        c=SimpleCookie()
        try:c.load(raw)
        except Exception:return None
        m=c.get("memoria_session"); return m.value if m else None
    def _cookie_header(self,t,max_age):
        p=[f"memoria_session={t}","Path=/","HttpOnly","SameSite=Strict",f"Max-Age={max_age}"]
        if self.config.cookie_secure:p.append("Secure")
        return "; ".join(p)
    def _redirect(self,l):self.send_response(303);self.send_header("Location",l);self.send_header("Cache-Control","no-store");self.send_header("Content-Length","0");self.end_headers()
    def _write_json(self,status,payload,extra_headers=None):
        data=json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode();self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(data)));self.send_header("X-Content-Type-Options","nosniff")
        for k,v in (extra_headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def _serve_static(self,f):
        if not f or not f.is_file():self._write_json(404,{"error":"asset_not_found"});return
        data=f.read_bytes();mime=mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript","application/json"}:mime+="; charset=utf-8"
        self.send_response(200);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(data)));self.send_header("X-Content-Type-Options","nosniff");self.send_header("Referrer-Policy","same-origin");self.send_header("Content-Security-Policy","default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'");self.end_headers()
        if self.command!="HEAD":self.wfile.write(data)
    def _read_body(self):
        try:n=int(self.headers.get("Content-Length","0"))
        except ValueError:self._write_json(400,{"error":"invalid_content_length"});return None
        if n<0 or n>self.config.max_request_bytes:self._write_json(413,{"error":"request_too_large"});return None
        return self.rfile.read(n) if n else b""
    def _proxy(self,target):
        base,path=target;p=urlsplit(self.path);url=base+path+("?"+p.query if p.query else "");body=self._read_body()
        if body is None:return
        h={k:v for k,v in self.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS and k.lower() not in {"host","content-length"}}
        if base==self.config.memoria_api_url and self.config.memoria_api_key:h["X-Memoria-Key"]=self.config.memoria_api_key
        if base==self.config.model_gateway_url and self.config.model_gateway_key:h["X-Model-Gateway-Key"]=self.config.model_gateway_key
        req=Request(url,data=body if body else None,headers=h,method=self.command); serialized=base==self.config.memoria_api_url and path=="/api/v1/episodes" and self.command=="POST"
        if serialized:self.episode_write_lock.acquire()
        try:
            with urlopen(req,timeout=self.config.proxy_timeout_seconds) as r:
                data=r.read();self.send_response(r.status)
                for k,v in r.headers.items():
                    if k.lower() not in HOP_BY_HOP_HEADERS and k.lower()!="content-length":self.send_header(k,v)
                self.send_header("Content-Length",str(len(data)));self.end_headers()
                if self.command!="HEAD":self.wfile.write(data)
        except HTTPError as e:
            data=e.read();self.send_response(e.code);self.send_header("Content-Type",e.headers.get("Content-Type","application/json; charset=utf-8"));self.send_header("Content-Length",str(len(data)));self.end_headers()
            if self.command!="HEAD":self.wfile.write(data)
        except (URLError,socket.timeout,TimeoutError):self._write_json(502,{"error":"upstream_unavailable"})
        finally:
            if serialized:self.episode_write_lock.release()
    def _login(self):
        if self.command!="POST":self._write_json(405,{"error":"method_not_allowed"},{"Allow":"POST"});return
        body=self._read_body()
        if body is None:return
        try:p=json.loads(body.decode());u=str(p.get("username",""));pw=str(p.get("password",""))
        except Exception:self._write_json(400,{"error":"invalid_request"});return
        r=self.auth.login(u,pw,self.client_address[0])
        if r.retry_after:self._write_json(429,{"error":"too_many_attempts"},{"Retry-After":str(r.retry_after)});return
        if not r.token:self._write_json(401,{"error":"invalid_credentials"});return
        self._write_json(200,{"status":"authenticated","username":self.config.admin_username},{"Set-Cookie":self._cookie_header(r.token,self.config.session_hours*3600)})
    def _logout(self):self.auth.logout(self._session_token());self._write_json(200,{"status":"logged_out"},{"Set-Cookie":self._cookie_header("",0)})
    def _component_health(self,b,p):
        try:
            with urlopen(Request(b+p,method="GET"),timeout=min(self.config.proxy_timeout_seconds,3.0)) as r:return {"status":"online" if r.status<400 else "degraded","code":r.status}
        except Exception:return {"status":"offline"}
    def _health(self):
        m=self._component_health(self.config.memoria_api_url,"/api/v1/health");b=self._component_health(self.config.bdr_explorer_url,"/api/health");g=self._component_health(self.config.model_gateway_url,"/health");states={m["status"],b["status"],g["status"]};k=self.knowledge.recent(limit=1)
        self._write_json(200,{"schema":"memoria-server-health/v1","status":"online" if states=={"online"} else "degraded","shell":{"status":"online","server_id":self.identity.snapshot()["server_id"]},"curiosity":{"status":self.curiosity.state.status,"enabled":self.curiosity.state.enabled},"knowledge":{"concepts":k["concepts"],"observations":k["observations"],"storage":"bdr-canonical"},"devices":self.devices.stats(),"components":{"memoria":m,"bdr_explorer":b,"model_gateway":g}})
    def _dispatch(self):
        p=urlsplit(self.path);path=p.path
        if path=="/api/server/v1/health":self._health();return
        if path=="/api/server/v1/login":self._login();return
        if self.device_auth.dispatch_public(self,path):return
        if self.device_auth.dispatch_device(self,path):return
        ok=self.auth.verify(self._session_token())
        if path=="/login":self._redirect("/") if ok else self._serve_static(SHELL_STATIC/"login.html");return
        if path in {"/login.css","/login.js"}:self._serve_static(static_target(path));return
        if not ok:self._write_json(401,{"error":"authentication_required"}) if path.startswith("/api/") else self._redirect("/login");return
        q=parse_qs(p.query)
        if path=="/api/server/v1/capabilities":
            if self.command not in {"GET","HEAD"}:self._write_json(405,{"error":"method_not_allowed"},{"Allow":"GET, HEAD"});return
            self._write_json(200,server_capabilities());return
        if path==IDENTITY_PATH:
            if self.command not in {"GET","HEAD"}:self._write_json(405,{"error":"method_not_allowed"},{"Allow":"GET, HEAD"});return
            self._write_json(200,self.identity.snapshot());return
        if path==AUDIT_PATH:
            if self.command not in {"GET","HEAD"}:self._write_json(405,{"error":"method_not_allowed"},{"Allow":"GET, HEAD"});return
            try:limit=int((q.get("limit") or ["100"])[0])
            except ValueError:limit=100
            self._write_json(200,self.audit.recent(limit));return
        if self.devices.dispatch(self,path,q):return
        if path=="/api/server/v1/epistemic/trajectories":
            if self.command not in {"GET","HEAD"}:self._write_json(405,{"error":"method_not_allowed"},{"Allow":"GET, HEAD"});return
            self._write_json(200,{"schema":"memoria-epistemic-trajectories/v1",**self.trajectories.snapshot()});return
        if self.growth.dispatch(self,path,q):return
        if self.site_ingest.dispatch(self,path,q):return
        if self.curiosity.dispatch(self,path,q):return
        if self.knowledge.dispatch(self,path,q):return
        if self.autotests.dispatch(self,path,q):return
        if path=="/api/server/v1/session":self._write_json(200,{"authenticated":True,"username":self.config.admin_username});return
        if path=="/api/server/v1/logout":self._write_json(405,{"error":"method_not_allowed"},{"Allow":"POST"}) if self.command!="POST" else self._logout();return
        t=proxy_target(self.config,path)
        if t:self._proxy(t);return
        a=static_target(path)
        if a:self._serve_static(a);return
        self._write_json(404,{"error":"route_not_found"})
    do_GET=_dispatch;do_HEAD=_dispatch;do_POST=_dispatch;do_PUT=_dispatch;do_PATCH=_dispatch;do_DELETE=_dispatch
    def log_message(self,format,*args):print("[memoria-server] "+(format%args))
def main():
    p=argparse.ArgumentParser(description="Memoria.ia Server shell");p.add_argument("--host");p.add_argument("--port",type=int);a=p.parse_args();c=ShellConfig.from_env()
    if a.host:c=ShellConfig(**{**c.__dict__,"host":a.host})
    if a.port:c=ShellConfig(**{**c.__dict__,"port":a.port})
    if not c.admin_password:raise RuntimeError("MEMORIA_SERVER_ADMIN_PASSWORD is required")
    ShellHandler.config=c;ShellHandler.auth=AuthManager(c.admin_username,c.admin_password,session_seconds=c.session_hours*3600);ShellHandler.autotests=AutonomousTestManager(c);ShellHandler.identity=ServerIdentity(c.server_data_dir);ShellHandler.audit=AuditLog(c.server_data_dir);ShellHandler.devices=DeviceRegistry(c.server_data_dir,ShellHandler.identity,ShellHandler.audit);ShellHandler.device_authority=DeviceAuthority(c.server_data_dir,ShellHandler.identity,ShellHandler.audit);ShellHandler.devices.set_certificate_issuer(ShellHandler.device_authority.issue_certificate);ShellHandler.device_auth=DeviceAuthManager(ShellHandler.devices,ShellHandler.device_authority,ShellHandler.audit);ShellHandler.knowledge=ServerKnowledge(str(Path(c.curiosity_data_dir).parent/"knowledge"));ShellHandler.trajectories=EpistemicTrajectoryStore(str(Path(c.curiosity_data_dir)/"trajectories"));ShellHandler.curiosity=TrajectoryGuidedCuriosityEngine(c,ShellHandler.knowledge,ShellHandler.trajectories);ShellHandler.site_ingest=SiteIngestManager(ShellHandler.curiosity,max_pages=200,max_depth=5);ShellHandler.growth=GrowthDiagnostics(c,ShellHandler.curiosity,ShellHandler.knowledge,write_lock=ShellHandler.episode_write_lock)
    kb=KnowledgeBDR(c.memoria_api_url,c.memoria_api_key,timeout=min(c.proxy_timeout_seconds,15.0),write_lock=ShellHandler.episode_write_lock);feedback=EpistemicFeedback(ShellHandler.knowledge,ShellHandler.curiosity,c.curiosity_data_dir,trajectories=ShellHandler.trajectories);learner=LearningWorker(ShellHandler.knowledge,c.curiosity_data_dir,bdr=kb,feedback=feedback);ShellHandler.curiosity.start();learner.start();server=ThreadingHTTPServer((c.host,c.port),ShellHandler);print(f"Memoria.ia Server: http://{c.host}:{c.port}");print("Modules: Memoria Admin + BDR Explorer + Device Registry + Device Auth + Audit Log + Curiosity Engine + Server Knowledge + Site Ingest + Growth Diagnostics + Epistemic Feedback + Epistemic Trajectories")
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:learner.stop();ShellHandler.curiosity.stop();server.server_close()
if __name__=="__main__":main()