"""One explicit model probe; print structural diagnostics only and never save an analysis."""
import asyncio
import json
import sys
import hashlib
import uuid
from pathlib import Path

import httpx
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.services import account_style_service as service
from config.db_config import sqlite_db_config


class Probe(httpx.AsyncBaseTransport):
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport(trust_env=False)
        self.records=[]
        self.replay={}
        if '--replay' in sys.argv:
            records=json.loads(Path(sys.argv[sys.argv.index('--replay')+1]).read_text(encoding='utf-8'))
            self.replay={r['request_sha256']:r['body'] for r in records}

    async def handle_async_request(self, request):
        request_body = json.loads(request.content)
        request_hash=hashlib.sha256(request.content).hexdigest()
        if request_hash in self.replay:
            print(json.dumps({'stage':'replay','kind':'previously captured response'}),flush=True)
            body=self.replay[request_hash]
            self.records.append({'request_sha256':request_hash,'body':body})
            return httpx.Response(200,json=body)
        if '--replay' in sys.argv:
            raise ValueError('Replay did not match; remote call blocked')
        inputs = json.loads(request_body['messages'][1]['content'])
        kind='batch' if inputs and 'post_id' in inputs[0] else 'summary'
        print(json.dumps({'stage':'request','kind':kind,'items':len(inputs),'max_tokens':request_body['max_tokens']}), flush=True)
        response = await self.inner.handle_async_request(request)
        await response.aread()
        metadata = {'stage':'response','http_status':response.status_code}
        try:
            body=response.json()
            if response.is_error:
                error=body.get('error',{})
                message=str(error.get('message','') if isinstance(error,dict) else error).lower()
                metadata['error_markers']=[word for word in ['context','token','maximum','length','max_tokens','unsupported','parameter','messages','model','limit'] if word in message]
                import re
                metadata['token_limits']=re.findall(r'\b(\d+)\s*(?:tokens?|token\b)',message)
                metadata['error_type']=error.get('type') if isinstance(error,dict) and error.get('type') in {'invalid_request_error','context_length_exceeded'} else 'other'
            choice=body.get('choices',[{}])[0]
            content=choice.get('message',{}).get('content') or ''
            metadata.update(finish_reason=choice.get('finish_reason'),usage=body.get('usage'),content_chars=len(content))
            if content.startswith('```'): content=content.split('\n',1)[1].rsplit('```',1)[0].strip()
            value=json.loads(content)
            metadata.update(assignment_count=len(value.get('topic_assignments',[])),topic_count=len(value.get('topic_labels',[])))
            if response.status_code==200 and choice.get('finish_reason')=='stop':
                self.records.append({'request_sha256':request_hash,'body':{'choices':[choice],'usage':body.get('usage')}})
        except (ValueError,KeyError,IndexError,TypeError): metadata['structured_content']=False
        print(json.dumps(metadata,ensure_ascii=False),flush=True)
        return response

    async def aclose(self): await self.inner.aclose()


async def main():
    if len(sys.argv)>2 and sys.argv[2].isdigit():
        original_source=service.source
        async def limited(*args,**kwargs):
            data=await original_source(*args,**kwargs)
            data['titles']=data['titles'][:int(sys.argv[2])]
            data['scope']['sampled']=len(data['titles'])
            return data
        service.source=limited
    connection=service.connection
    async def readonly(path,*,write=False):
        if write: raise service.ProfileUnavailable('诊断已完成；主动阻止保存')
        return await connection(path)
    service.connection=readonly
    probe=Probe()
    try:
        await service.analyze_style(sqlite_db_config['db_path'],int(sys.argv[1]) if len(sys.argv)>1 else 1,transport=probe)
        print('cached result; no call')
    except Exception as exc:
        cause=exc.__cause__ or exc
        detail={'stage':'validation','exception_type':type(cause).__name__}
        if isinstance(cause,ValidationError):
            detail['fields']=[{'path':list(e['loc']),'type':e['type']} for e in cause.errors()]
        elif isinstance(cause,(ValueError,service.ProfileUnavailable,service.GroupingError)):
            detail['reason']=str(cause)[:120]
        print(json.dumps(detail,ensure_ascii=False),flush=True)
    finally:
        output=Path(__file__).resolve().parents[1]/'tmp'/('style-model-probe-'+uuid.uuid4().hex[:12])
        output.mkdir(exist_ok=False)
        with (output/'responses.json').open('x',encoding='utf-8') as file:
            json.dump(probe.records,file,ensure_ascii=False)
        print(json.dumps({'response_evidence':str(output/'responses.json')},ensure_ascii=False),flush=True)


if __name__=='__main__': asyncio.run(main())
