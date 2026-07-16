# Preflight

## Git

```text
?? docs/handoffs/
?? experiments/2026-07-08--langfuse--official-plugin-real-session/runs/
```

## LangFuse status

```text
NAME                         IMAGE                                    COMMAND                  SERVICE           CREATED        STATUS                  PORTS
langfuse-clickhouse-1        docker.io/clickhouse/clickhouse-server   "/entrypoint.sh"         clickhouse        19 hours ago   Up 19 hours (healthy)   8123/tcp, 9000/tcp, 9009/tcp
langfuse-langfuse-web-1      docker.io/langfuse/langfuse:3            "dumb-init -- ./web/…"   langfuse-web      19 hours ago   Up 19 hours             0.0.0.0:3000->3000/tcp, [::]:3000->3000/tcp
langfuse-langfuse-worker-1   docker.io/langfuse/langfuse-worker:3     "dumb-init -- ./work…"   langfuse-worker   19 hours ago   Up 19 hours             3030/tcp
langfuse-minio-1             cgr.dev/chainguard/minio                 "sh -c 'mkdir -p /da…"   minio             19 hours ago   Up 19 hours (healthy)   
langfuse-postgres-1          docker.io/postgres:17                    "docker-entrypoint.s…"   postgres          19 hours ago   Up 19 hours (healthy)   5432/tcp
langfuse-redis-1             docker.io/redis:7                        "docker-entrypoint.s…"   redis             19 hours ago   Up 19 hours (healthy)   6379/tcp
```

## Tool versions

```text
/Users/neural/.local/bin/claude
2.1.204 (Claude Code)
/opt/homebrew/bin/codex
codex-cli 0.142.5
v22.17.1
uv 0.11.6 (65950801c 2026-04-09 aarch64-apple-darwin)
Python 3.14.4
```

## Claude plugins before

```text
Installed plugins:

  ❯ delegation@agentic-primitives
    Version: 1.2.0
    Scope: user
    Status: ✔ enabled

  ❯ docs@agentic-primitives
    Version: 1.1.0
    Scope: user
    Status: ✔ enabled

  ❯ experiments@agentic-primitives
    Version: 1.0.0
    Scope: user
    Status: ✔ enabled

  ❯ frontend-design@claude-plugins-official
    Version: unknown
    Scope: user
    Status: ✔ enabled

  ❯ hindsight-memory@hindsight
    Version: 0.6.4
    Scope: user
    Status: ✔ enabled

  ❯ meta@agentic-primitives
    Version: 1.2.0
    Scope: user
    Status: ✔ enabled

  ❯ notifications@agentic-primitives
    Version: 0.4.1
    Scope: user
    Status: ✔ enabled

  ❯ pyright-lsp@claude-plugins-official
    Version: 1.0.0
    Scope: user
    Status: ✔ enabled

  ❯ ralph-loop@claude-plugins-official
    Version: 1.0.0
    Scope: user
    Status: ✘ disabled

  ❯ sdlc@agentic-primitives
    Version: 1.4.0
    Scope: user
    Status: ✔ enabled

  ❯ software-leverage-points@software-leverage-points
    Version: 0.1.0
    Scope: user
    Status: ✔ enabled

  ❯ superpowers@claude-plugins-official
    Version: 6.1.1
    Scope: user
    Status: ✔ enabled

  ❯ syntropic137@syntropic137
    Version: 0.11.5
    Scope: user
    Status: ✔ enabled

  ❯ ui-ux-pro-max@ui-ux-pro-max-skill
    Version: 2.0.1
    Scope: user
    Status: ✔ enabled

  ❯ warp@claude-code-warp
    Version: 2.1.0
    Scope: user
    Status: ✔ enabled

```

## Codex plugins before

```text
Marketplace `openai-primary-runtime`
/Users/neural/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/.agents/plugins/marketplace.json

PLUGIN                                   STATUS              VERSION       PATH                                                                                                             
documents@openai-primary-runtime         installed, enabled  26.630.12135  /Users/neural/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/plugins/documents       
pdf@openai-primary-runtime               installed, enabled  26.630.12135  /Users/neural/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/plugins/pdf             
spreadsheets@openai-primary-runtime      installed, enabled  26.630.12135  /Users/neural/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/plugins/spreadsheets    
presentations@openai-primary-runtime     installed, enabled  26.630.12135  /Users/neural/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/plugins/presentations   
template-creator@openai-primary-runtime  installed, enabled  26.630.12135  /Users/neural/.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/plugins/template-creator

Marketplace `openai-bundled`
/Users/neural/.codex/.tmp/bundled-marketplaces/openai-bundled/.agents/plugins/marketplace.json

PLUGIN                            STATUS              VERSION       PATH                                                                                   
browser@openai-bundled            installed, enabled  26.616.71553  /Users/neural/.codex/.tmp/bundled-marketplaces/openai-bundled/plugins/browser          
chrome@openai-bundled             not installed                     /Users/neural/.codex/.tmp/bundled-marketplaces/openai-bundled/plugins/chrome           
computer-use@openai-bundled       not installed                     /Users/neural/.codex/.tmp/bundled-marketplaces/openai-bundled/plugins/computer-use     
record-and-replay@openai-bundled  not installed                     /Users/neural/.codex/.tmp/bundled-marketplaces/openai-bundled/plugins/record-and-replay
latex@openai-bundled              not installed                     /Users/neural/.codex/.tmp/bundled-marketplaces/openai-bundled/plugins/latex            

Marketplace `openai-curated`
/Users/neural/.codex/.tmp/plugins/.agents/plugins/marketplace.json

PLUGIN                                       STATUS              VERSION   PATH                                                                  
linear@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/linear                      
atlassian-rovo@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/atlassian-rovo              
google-calendar@openai-curated               not installed                 /Users/neural/.codex/.tmp/plugins/plugins/google-calendar             
gmail@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/gmail                       
slack@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/slack                       
teams@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/teams                       
sharepoint@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/sharepoint                  
outlook-email@openai-curated                 not installed                 /Users/neural/.codex/.tmp/plugins/plugins/outlook-email               
outlook-calendar@openai-curated              not installed                 /Users/neural/.codex/.tmp/plugins/plugins/outlook-calendar            
canva@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/canva                       
figma@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/figma                       
hugging-face@openai-curated                  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/hugging-face                
jam@openai-curated                           not installed                 /Users/neural/.codex/.tmp/plugins/plugins/jam                         
netlify@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/netlify                     
stripe@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/stripe                      
vercel@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/vercel                      
game-studio@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/game-studio                 
superpowers@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/superpowers                 
box@openai-curated                           not installed                 /Users/neural/.codex/.tmp/plugins/plugins/box                         
github@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/github                      
circleci@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/circleci                    
google-drive@openai-curated                  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/google-drive                
deepnote@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/deepnote                    
notion@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/notion                      
cloudflare@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/cloudflare                  
sentry@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/sentry                      
build-ios-apps@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/build-ios-apps              
build-macos-apps@openai-curated              not installed                 /Users/neural/.codex/.tmp/plugins/plugins/build-macos-apps            
build-web-apps@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/build-web-apps              
build-web-data-visualization@openai-curated  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/build-web-data-visualization
test-android-apps@openai-curated             not installed                 /Users/neural/.codex/.tmp/plugins/plugins/test-android-apps           
life-science-research@openai-curated         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/life-science-research       
zotero@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/zotero                      
expo@openai-curated                          not installed                 /Users/neural/.codex/.tmp/plugins/plugins/expo                        
coderabbit@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/coderabbit                  
neon-postgres@openai-curated                 not installed                 /Users/neural/.codex/.tmp/plugins/plugins/neon-postgres               
remotion@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/remotion                    
plugin-eval@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/plugin-eval                 
alpaca@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/alpaca                      
amplitude@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/amplitude                   
attio@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/attio                       
binance@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/binance                     
biorender@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/biorender                   
brand24@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/brand24                     
brex@openai-curated                          not installed                 /Users/neural/.codex/.tmp/plugins/plugins/brex                        
carta-crm@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/carta-crm                   
cb-insights@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/cb-insights                 
channel99@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/channel99                   
circleback@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/circleback                  
clickup@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/clickup                     
cloudinary@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/cloudinary                  
cogedim@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/cogedim                     
common-room@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/common-room                 
conductor@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/conductor                   
coupler-io@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/coupler-io                  
coveo@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/coveo                       
cube@openai-curated                          not installed                 /Users/neural/.codex/.tmp/plugins/plugins/cube                        
daloopa@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/daloopa                     
demandbase@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/demandbase                  
dnb-finance-analytics@openai-curated         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/dnb-finance-analytics       
docket@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/docket                      
domotz-preview@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/domotz-preview              
dovetail@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/dovetail                    
dow-jones-factiva@openai-curated             not installed                 /Users/neural/.codex/.tmp/plugins/plugins/dow-jones-factiva           
egnyte@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/egnyte                      
finn@openai-curated                          not installed                 /Users/neural/.codex/.tmp/plugins/plugins/finn                        
fireflies@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/fireflies                   
fyxer@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/fyxer                       
govtribe@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/govtribe                    
granola@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/granola                     
happenstance@openai-curated                  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/happenstance                
help-scout@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/help-scout                  
hex@openai-curated                           not installed                 /Users/neural/.codex/.tmp/plugins/plugins/hex                         
highlevel@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/highlevel                   
hostinger@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/hostinger                   
hubspot@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/hubspot                     
keybid-puls@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/keybid-puls                 
marcopolo@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/marcopolo                   
mem@openai-curated                           not installed                 /Users/neural/.codex/.tmp/plugins/plugins/mem                         
monday-com@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/monday-com                  
moody-s@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/moody-s                     
morningstar@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/morningstar                 
motherduck@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/motherduck                  
mt-newswires@openai-curated                  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/mt-newswires                
myregistry-com@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/myregistry-com              
network-solutions@openai-curated             not installed                 /Users/neural/.codex/.tmp/plugins/plugins/network-solutions           
omni-analytics@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/omni-analytics              
otter-ai@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/otter-ai                    
particl-market-research@openai-curated       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/particl-market-research     
pipedrive@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/pipedrive                   
pitchbook@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/pitchbook                   
policynote@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/policynote                  
pylon@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/pylon                       
quartr@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/quartr                      
quicknode@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/quicknode                   
ranked-ai@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/ranked-ai                   
razorpay@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/razorpay                    
read-ai@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/read-ai                     
readwise@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/readwise                    
responsive@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/responsive                  
scite@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/scite                       
semrush@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/semrush                     
sendgrid@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/sendgrid                    
setu-bharat-connect-billpay@openai-curated   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/setu-bharat-connect-billpay 
signnow@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/signnow                     
skywatch@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/skywatch                    
statsig@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/statsig                     
streak@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/streak                      
taxdown@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/taxdown                     
teamwork-com@openai-curated                  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/teamwork-com                
third-bridge@openai-curated                  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/third-bridge                
tinman-ai@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/tinman-ai                   
united-rentals@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/united-rentals              
vantage@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/vantage                     
waldo@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/waldo                       
weatherpromise@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/weatherpromise              
windsor-ai@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/windsor-ai                  
yepcode@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/yepcode                     
render@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/render                      
temporal@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/temporal                    
hyperframes@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/hyperframes                 
heygen@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/heygen                      
supabase@openai-curated                      installed, enabled  d6169bef  /Users/neural/.codex/.tmp/plugins/plugins/supabase                    
codex-security@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/codex-security              
twilio-developer-kit@openai-curated          not installed                 /Users/neural/.codex/.tmp/plugins/plugins/twilio-developer-kit        
openai-developers@openai-curated             not installed                 /Users/neural/.codex/.tmp/plugins/plugins/openai-developers           
asana@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/asana                       
datadog@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/datadog                     
zoom@openai-curated                          not installed                 /Users/neural/.codex/.tmp/plugins/plugins/zoom                        
similarweb@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/similarweb                  
lseg@openai-curated                          not installed                 /Users/neural/.codex/.tmp/plugins/plugins/lseg                        
s-p@openai-curated                           not installed                 /Users/neural/.codex/.tmp/plugins/plugins/s-p                         
datasite@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/datasite                    
factset@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/factset                     
zoominfo@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/zoominfo                    
docusign@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/docusign                    
mixpanel@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/mixpanel                    
mixpanel-headless@openai-curated             not installed                 /Users/neural/.codex/.tmp/plugins/plugins/mixpanel-headless           
aiera@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/aiera                       
close@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/close                       
apollo@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/apollo                      
meticulate@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/meticulate                  
thoughtspot@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/thoughtspot                 
midpage@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/midpage                     
clay@openai-curated                          not installed                 /Users/neural/.codex/.tmp/plugins/plugins/clay                        
calendly@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/calendly                    
rox@openai-curated                           not installed                 /Users/neural/.codex/.tmp/plugins/plugins/rox                         
hg-insights@openai-curated                   not installed                 /Users/neural/.codex/.tmp/plugins/plugins/hg-insights                 
airtable@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/airtable                    
convex@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/convex                      
outreach@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/outreach                    
shutterstock@openai-curated                  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/shutterstock                
replit@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/replit                      
lovable@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/lovable                     
quickbooks@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/quickbooks                  
intercom@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/intercom                    
chronograph-lp@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/chronograph-lp              
nvidia@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/nvidia                      
posthog@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/posthog                     
actively@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/actively                    
zoho@openai-curated                          not installed                 /Users/neural/.codex/.tmp/plugins/plugins/zoho                        
fiscal-ai@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/fiscal-ai                   
picsart@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/picsart                     
alation@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/alation                     
fal@openai-curated                           not installed                 /Users/neural/.codex/.tmp/plugins/plugins/fal                         
hebbia@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/hebbia                      
wix@openai-curated                           not installed                 /Users/neural/.codex/.tmp/plugins/plugins/wix                         
base44@openai-curated                        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/base44                      
ngs-analysis@openai-curated                  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/ngs-analysis                
superhuman@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/superhuman                  
shopify@openai-curated                       not installed                 /Users/neural/.codex/.tmp/plugins/plugins/shopify                     
magicpath@openai-curated                     not installed                 /Users/neural/.codex/.tmp/plugins/plugins/magicpath                   
brighthire@openai-curated                    not installed                 /Users/neural/.codex/.tmp/plugins/plugins/brighthire                  
catalyst-by-zoho@openai-curated              not installed                 /Users/neural/.codex/.tmp/plugins/plugins/catalyst-by-zoho            
glean@openai-curated                         not installed                 /Users/neural/.codex/.tmp/plugins/plugins/glean                       
chronograph-gp@openai-curated                not installed                 /Users/neural/.codex/.tmp/plugins/plugins/chronograph-gp              
openai-ads-conversions@openai-curated        not installed                 /Users/neural/.codex/.tmp/plugins/plugins/openai-ads-conversions      
boltz-api-cli@openai-curated                 not installed                 /Users/neural/.codex/.tmp/plugins/plugins/boltz-api-cli               
replayio@openai-curated                      not installed                 /Users/neural/.codex/.tmp/plugins/plugins/replayio                    
digitalocean@openai-curated                  not installed                 /Users/neural/.codex/.tmp/plugins/plugins/digitalocean                
```

## Local LangFuse config redacted

```text
LANGFUSE_BASE_URL=http://localhost:3000
LANGFUSE_INIT_PROJECT_ID=agentic-primitives-local-project
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-REDACTED...
LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-REDACTED
```
