"""Async Gemini REST client with key x model rotation, rate-limit handling and disk cache."""
import asyncio, base64, hashlib, json, os, random, re, time
from pathlib import Path
import aiohttp

from common import CACHE, SCRATCH, log

ENV = Path('/home/luongminhthu/Documents/code/my_app/_shared/secrets/google.env')
STATE_FILE = SCRATCH / 'gemini_state.json'

FLASH = ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.6-flash', 'gemini-3.5-flash',
         'gemini-3-flash-preview', 'gemini-flash-latest']
LITE = ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-flash-lite-latest',
        'gemini-3.1-flash-lite-preview', 'gemini-2.5-flash', 'gemini-2.5-flash-lite']
GEMMA = ['gemma-4-31b-it', 'gemma-4-26b-a4b-it']
ALL = FLASH + LITE + GEMMA


def _load_keys():
    keys = os.environ.get('GEMINI_API_KEYS')
    if not keys:
        for line in ENV.read_text().splitlines():
            if line.startswith('GEMINI_API_KEYS='):
                keys = line.split('=', 1)[1].strip().strip('"')
    return [k.strip() for k in keys.split(',') if k.strip()]


def next_reset():
    # free-tier daily quotas reset at midnight America/Los_Angeles
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo('America/Los_Angeles'))
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=2, second=0, microsecond=0)
    return nxt.timestamp()


class NoCapacity(Exception):
    pass


class Slot:
    def __init__(self, ki, model):
        self.ki, self.model = ki, model
        self.dead = False
        self.day_until = 0.0
        self.cool_until = 0.0
        self.inflight = 0
        self.ok = 0

    @property
    def name(self):
        return f'{self.ki}:{self.model}'


class Gemini:
    def __init__(self, per_slot=2):
        self.keys = _load_keys()
        self.per_slot = per_slot
        self.slots = {}
        self.key_dead = set()
        st = {}
        try:
            st = json.loads(STATE_FILE.read_text())
        except Exception:
            pass
        now = time.time()
        for ki in range(len(self.keys)):
            for m in ALL:
                s = Slot(ki, m)
                v = st.get(s.name, {})
                s.dead = v.get('dead', False)
                s.day_until = v.get('day_until', 0) if v.get('day_until', 0) > now else 0
                self.slots[s.name] = s
        self.session = None
        self.stats = {'calls': 0, 'ok': 0, 'r429': 0, 'err': 0, 'cache': 0}
        self._last_save = 0

    def _save_state(self, force=False):
        if not force and time.time() - self._last_save < 10:
            return
        self._last_save = time.time()
        # merge with other processes' view
        try:
            st = json.loads(STATE_FILE.read_text())
        except Exception:
            st = {}
        for s in self.slots.values():
            if s.dead or s.day_until > time.time():
                st[s.name] = {'dead': s.dead, 'day_until': s.day_until}
        tmp = STATE_FILE.with_suffix('.tmp%d' % os.getpid())
        tmp.write_text(json.dumps(st))
        tmp.rename(STATE_FILE)

    def _refresh_state(self):
        try:
            st = json.loads(STATE_FILE.read_text())
        except Exception:
            return
        for k, v in st.items():
            s = self.slots.get(k)
            if s:
                s.dead = s.dead or v.get('dead', False)
                s.day_until = max(s.day_until, v.get('day_until', 0))

    async def _sess(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600))
        return self.session

    def _pick(self, models):
        now = time.time()
        waiting = False
        for m in models:
            cands = [s for s in (self.slots[f'{ki}:{m}'] for ki in range(len(self.keys)))
                     if not s.dead and s.ki not in self.key_dead and s.day_until < now]
            if not cands:
                continue
            ready = [s for s in cands if s.cool_until < now and s.inflight < self.per_slot]
            if ready:
                random.shuffle(ready)
                ready.sort(key=lambda s: s.inflight)
                return ready[0]
            waiting = True
        if waiting:
            return None
        raise NoCapacity(f'no capacity for {models}')

    async def generate(self, parts, models=FLASH, schema=None, cache_key=None, temperature=None,
                       system=None, max_tries=40, thinking=None):
        if cache_key:
            cp = CACHE / (cache_key + '.json')
            if cp.exists():
                try:
                    self.stats['cache'] += 1
                    return json.loads(cp.read_text())
                except Exception:
                    pass
        body = {'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': {'maxOutputTokens': 65536}}
        if system:
            body['systemInstruction'] = {'parts': [{'text': system}]}
        if schema is not None:
            body['generationConfig']['responseMimeType'] = 'application/json'
            body['generationConfig']['responseSchema'] = schema
        if temperature is not None:
            body['generationConfig']['temperature'] = temperature
        sess = await self._sess()
        tries = 0
        last_err = None
        while tries < max_tries:
            try:
                slot = self._pick(models)
            except NoCapacity:
                self._refresh_state()
                raise
            if slot is None:
                await asyncio.sleep(2 + random.random() * 3)
                continue
            tries += 1
            slot.inflight += 1
            self.stats['calls'] += 1
            try:
                rb = body
                if slot.model.startswith('gemma') and schema is not None:
                    rb = json.loads(json.dumps(body))
                    rb['generationConfig'].pop('responseSchema', None)
                    rb['contents'][0]['parts'].append({'text': 'Chỉ trả về JSON hợp lệ theo schema sau (không kèm giải thích ngoài JSON): ' + json.dumps(schema, ensure_ascii=False)})
                async with sess.post(
                        f'https://generativelanguage.googleapis.com/v1beta/models/{slot.model}:generateContent',
                        json=rb, headers={'x-goog-api-key': self.keys[slot.ki]}) as r:
                    txt = await r.text()
                    status = r.status
            except Exception as e:
                slot.inflight -= 1
                last_err = f'net {type(e).__name__}'
                slot.cool_until = time.time() + 10
                await asyncio.sleep(2)
                continue
            slot.inflight -= 1
            if status == 200:
                try:
                    j = json.loads(txt)
                    cand = j['candidates'][0]
                    out = ''.join(p.get('text', '') for p in cand['content']['parts'] if not p.get('thought'))
                    if schema is not None:
                        o = out.strip()
                        if o.startswith('```'):
                            o = re.sub(r'^```(json)?\s*|\s*```$', '', o)
                        res = json.loads(o)
                        if isinstance(res, list) and schema.get('required'):
                            res = {schema['required'][0]: res}
                    else:
                        res = out
                except Exception as e:
                    fr = ''
                    try:
                        fr = j['candidates'][0].get('finishReason', '')
                    except Exception:
                        fr = str(j.get('promptFeedback', ''))[:100]
                    last_err = f'bad output {slot.model} {fr} {type(e).__name__}'
                    self.stats['err'] += 1
                    if tries >= 4 and fr == 'MAX_TOKENS':
                        break
                    continue
                self.stats['ok'] += 1
                slot.ok += 1
                wrapped = {'model': slot.model, 'result': res}
                if cache_key:
                    cp = CACHE / (cache_key + '.json')
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    tmp = cp.with_suffix('.tmp%d' % os.getpid())
                    tmp.write_text(json.dumps(wrapped, ensure_ascii=False))
                    tmp.rename(cp)
                return wrapped
            if status == 429:
                self.stats['r429'] += 1
                tries -= 1
                await asyncio.sleep(0.2)
                if 'PerDay' in txt or 'per day' in txt.lower():
                    slot.day_until = next_reset()
                    self._save_state()
                else:
                    m = re.search(r'"retryDelay":\s*"(\d+)', txt)
                    slot.cool_until = time.time() + (int(m.group(1)) if m else 30) + random.random() * 5
                continue
            if status in (401, 403):
                if 'API_KEY' in txt or status == 401 or 'PERMISSION' in txt:
                    self.key_dead.add(slot.ki)
                slot.dead = True
                self._save_state()
                last_err = f'{status}'
                continue
            if status == 404:
                slot.dead = True
                self._save_state()
                continue
            if status in (500, 502, 503, 504):
                slot.cool_until = time.time() + 15
                last_err = f'{status} {slot.model}'
                await asyncio.sleep(1)
                continue
            # 400 etc.
            last_err = f'{status} {slot.model} {txt[:300]}'
            log('gemini', last_err[:200])
            self.stats['err'] += 1
            if status == 400 and ('schema' in txt.lower() or 'mime' in txt.lower() or 'thinking' in txt.lower()):
                slot.dead = True  # model doesn't support this request shape
                continue
            if tries >= 3:
                break
        raise RuntimeError(f'gemini failed: {last_err}')


def file_part(path, mime):
    return {'inlineData': {'mimeType': mime, 'data': base64.b64encode(Path(path).read_bytes()).decode()}}


def sha(data):
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()[:24]
