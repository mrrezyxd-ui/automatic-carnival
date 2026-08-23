from http.server import BaseHTTPRequestHandler
import json
import re
import requests
from datetime import datetime, timezone


class handler(BaseHTTPRequestHandler):

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')

    def _json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):

        # Read body
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            self._json(400, {'success': False, 'error': 'Empty request body'})
            return

        try:
            data = json.loads(self.rfile.read(length))
        except Exception:
            self._json(400, {'success': False, 'error': 'Invalid JSON body'})
            return

        if not isinstance(data, dict):
            self._json(400, {'success': False, 'error': 'Request body must be a JSON object'})
            return

        # Validate webhook URL
        webhook_url = (data.get('webhook_url') or '').strip()
        if not webhook_url:
            self._json(400, {'success': False, 'error': 'Webhook URL is required'})
            return

        if not re.match(r'^https://(discord\.com|discordapp\.com)/api/webhooks/\d+/[a-zA-Z0-9_-]+$', webhook_url):
            self._json(400, {'success': False, 'error': 'Invalid webhook URL format'})
            return

        # Build payload
        payload = {}

        username = (data.get('username') or '').strip()
        if username:
            payload['username'] = username[:80]

        avatar_url = (data.get('avatar_url') or '').strip()
        if avatar_url:
            payload['avatar_url'] = avatar_url[:2048]

        content = (data.get('content') or '').strip()
        if content:
            payload['content'] = content[:2000]

        # Build embed
        embed_data = data.get('embed')
        if isinstance(embed_data, dict):
            embed = {}

            title = (embed_data.get('title') or '').strip()
            if title:
                embed['title'] = title[:256]

            title_url = (embed_data.get('title_url') or '').strip()
            if title_url:
                embed['url'] = title_url[:2048]

            description = (embed_data.get('description') or '').strip()
            if description:
                embed['description'] = description[:4096]

            color_raw = (embed_data.get('color') or '').strip()
            if color_raw:
                try:
                    c = color_raw.lstrip('#')
                    if c.isdigit():
                        embed['color'] = int(c)
                    elif len(c) in (3, 6) and all(ch in '0123456789abcdefABCDEF' for ch in c):
                        embed['color'] = int(c, 16)
                    else:
                        embed['color'] = int(color_raw)
                except (ValueError, TypeError):
                    pass

            author_name = (embed_data.get('author_name') or '').strip()
            author_icon = (embed_data.get('author_icon') or '').strip()
            author_url = (embed_data.get('author_url') or '').strip()
            if author_name or author_icon:
                a = {}
                if author_name:
                    a['name'] = author_name[:256]
                if author_url:
                    a['url'] = author_url[:2048]
                if author_icon:
                    a['icon_url'] = author_icon[:2048]
                embed['author'] = a

            thumbnail = (embed_data.get('thumbnail') or '').strip()
            if thumbnail:
                embed['thumbnail'] = {'url': thumbnail[:2048]}

            image = (embed_data.get('image') or '').strip()
            if image:
                embed['image'] = {'url': image[:2048]}

            footer_text = (embed_data.get('footer_text') or '').strip()
            footer_icon = (embed_data.get('footer_icon') or '').strip()
            if footer_text or footer_icon:
                f = {}
                if footer_text:
                    f['text'] = footer_text[:2048]
                if footer_icon:
                    f['icon_url'] = footer_icon[:2048]
                embed['footer'] = f

            ts = embed_data.get('timestamp')
            if ts:
                if isinstance(ts, bool) and ts:
                    embed['timestamp'] = datetime.now(timezone.utc).isoformat()
                elif isinstance(ts, str) and ts.strip():
                    embed['timestamp'] = ts.strip()

            raw_fields = embed_data.get('fields')
            if isinstance(raw_fields, list):
                ef = []
                for fld in raw_fields[:25]:
                    if not isinstance(fld, dict):
                        continue
                    fn = (fld.get('name') or '').strip()
                    fv = (fld.get('value') or '').strip()
                    if fn and fv:
                        ef.append({
                            'name': fn[:256],
                            'value': fv[:1024],
                            'inline': bool(fld.get('inline', False))
                        })
                if ef:
                    embed['fields'] = ef

            if embed:
                payload['embeds'] = [embed]

        if not payload:
            self._json(400, {'success': False, 'error': 'Nothing to send. Add content or an embed.'})
            return

        # Send to Discord
        try:
            resp = requests.post(webhook_url, json=payload, timeout=15)
            if resp.status_code in (200, 204):
                self._json(200, {'success': True, 'message': 'Webhook sent successfully!'})
            else:
                try:
                    err = resp.json()
                    msg = err.get('message', f'Discord API error: {resp.status_code}')
                except Exception:
                    msg = f'Discord API returned status {resp.status_code}'
                self._json(resp.status_code, {'success': False, 'error': msg})
        except requests.exceptions.Timeout:
            self._json(504, {'success': False, 'error': 'Request timed out.'})
        except requests.exceptions.ConnectionError:
            self._json(502, {'success': False, 'error': 'Could not connect to Discord.'})
        except Exception as e:
            self._json(500, {'success': False, 'error': f'Unexpected error: {str(e)}'})