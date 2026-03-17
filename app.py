#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
djakchat Lite — Web Server
سيرفر ويب كامل يعمل في المتصفح مثل الفيسبوك
"""

from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import json, os, hashlib, uuid, base64
from datetime import datetime

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'djakchat_secret_2024_djakjak')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DATA_FILE = 'data.json'

# ═══════════════════════════════════════
# قاعدة البيانات
# ═══════════════════════════════════════
def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {"users":{}, "posts":[], "messages":{}, "friends":{}, "requests":{}}

def save(db):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def hpw(pw): return hashlib.sha256(pw.encode()).hexdigest()
def now(): return datetime.now().strftime("%Y-%m-%d %H:%M")
def ts(): return datetime.now().strftime("%H:%M")

# مستخدمون متصلون حالياً {username: socket_id}
online = {}

# ═══════════════════════════════════════
# API — المصادقة
# ═══════════════════════════════════════
@app.route('/api/register', methods=['POST'])
def register():
    d  = request.json
    nm = d.get('username','').strip()
    pw = d.get('password','').strip()
    if not nm or len(nm) < 2: return jsonify(ok=False, msg="الاسم قصير")
    if not pw or len(pw) < 4: return jsonify(ok=False, msg="كلمة المرور قصيرة (4+ أحرف)")
    db = load()
    if nm in db['users']: return jsonify(ok=False, msg="الاسم مستخدم بالفعل")
    db['users'][nm] = {"pw": hpw(pw), "bio":"", "avatar":"", "joined": now()}
    db['friends'][nm] = []
    db['requests'][nm] = []
    save(db)
    session['user'] = nm
    return jsonify(ok=True, username=nm)

@app.route('/api/login', methods=['POST'])
def login():
    d  = request.json
    nm = d.get('username','').strip()
    pw = d.get('password','').strip()
    db = load()
    u  = db['users'].get(nm)
    if not u or u['pw'] != hpw(pw):
        return jsonify(ok=False, msg="اسم أو كلمة مرور خاطئة")
    session['user'] = nm
    return jsonify(ok=True, username=nm)

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify(ok=True)

@app.route('/api/me')
def me():
    u = session.get('user')
    if not u: return jsonify(ok=False)
    db = load()
    user = db['users'].get(u, {})
    return jsonify(ok=True, username=u, bio=user.get('bio',''),
                   avatar=user.get('avatar',''),
                   friends=db['friends'].get(u,[]),
                   requests=db['requests'].get(u,[]),
                   online=list(online.keys()))

# ═══════════════════════════════════════
# API — المنشورات
# ═══════════════════════════════════════
@app.route('/api/posts', methods=['GET'])
def get_posts():
    u    = session.get('user')
    db   = load()
    mode = request.args.get('mode','feed')
    if mode == 'explore':
        posts = db['posts'][:40]
    else:
        friends = db['friends'].get(u,[]) if u else []
        posts = [p for p in db['posts'] if p['author']==u or p['author'] in friends][:30]
    return jsonify(posts=posts)

@app.route('/api/posts', methods=['POST'])
def new_post():
    u = session.get('user')
    if not u: return jsonify(ok=False, msg="غير مسجّل")
    d = request.json
    text  = d.get('text','').strip()[:2000]
    media = d.get('media','')
    mtype = d.get('mtype','')
    if not text and not media: return jsonify(ok=False, msg="المنشور فارغ")
    db = load()
    post = {"id": str(uuid.uuid4())[:8], "author": u,
            "text": text, "media": media, "mtype": mtype,
            "likes":[], "comments":[], "time": now()}
    db['posts'].insert(0, post)
    db['posts'] = db['posts'][:300]
    save(db)
    socketio.emit('new_post', post)
    return jsonify(ok=True, post=post)

@app.route('/api/posts/<pid>/like', methods=['POST'])
def like_post(pid):
    u = session.get('user')
    if not u: return jsonify(ok=False)
    db = load()
    for p in db['posts']:
        if p['id'] == pid:
            if u in p['likes']: p['likes'].remove(u)
            else: p['likes'].append(u)
            save(db)
            socketio.emit('post_liked', {'pid':pid,'likes':p['likes']})
            return jsonify(ok=True, likes=p['likes'], liked=u in p['likes'])
    return jsonify(ok=False)

@app.route('/api/posts/<pid>/comment', methods=['POST'])
def comment_post(pid):
    u = session.get('user')
    if not u: return jsonify(ok=False)
    text = request.json.get('text','').strip()[:500]
    if not text: return jsonify(ok=False)
    db = load()
    for p in db['posts']:
        if p['id'] == pid:
            c = {"author":u,"text":text,"time":ts()}
            p['comments'].append(c)
            save(db)
            socketio.emit('new_comment', {'pid':pid,'comment':c})
            return jsonify(ok=True, comment=c)
    return jsonify(ok=False)

@app.route('/api/posts/<pid>', methods=['DELETE'])
def delete_post(pid):
    u = session.get('user')
    db = load()
    db['posts'] = [p for p in db['posts'] if not (p['id']==pid and p['author']==u)]
    save(db)
    socketio.emit('post_deleted', {'pid':pid})
    return jsonify(ok=True)

# ═══════════════════════════════════════
# API — الأصدقاء
# ═══════════════════════════════════════
@app.route('/api/users/search')
def search_users():
    u = session.get('user')
    q = request.args.get('q','').lower()
    db = load()
    results = [n for n in db['users'] if q in n.lower() and n != u][:10]
    return jsonify(results=results)

@app.route('/api/friends/request', methods=['POST'])
def friend_request():
    u  = session.get('user')
    to = request.json.get('to','')
    db = load()
    if to not in db['users']: return jsonify(ok=False, msg="المستخدم غير موجود")
    if to in db['friends'].get(u,[]): return jsonify(ok=False, msg="صديق بالفعل")
    if u in db['requests'].get(to,[]): return jsonify(ok=False, msg="تم الإرسال")
    db['requests'].setdefault(to,[]).append(u)
    save(db)
    if to in online:
        socketio.emit('friend_request', {'from':u}, room=online[to])
    return jsonify(ok=True, msg=f"أُرسل طلب لـ {to}")

@app.route('/api/friends/accept', methods=['POST'])
def accept_friend():
    u   = session.get('user')
    frm = request.json.get('from','')
    db  = load()
    reqs = db['requests'].get(u,[])
    if frm not in reqs: return jsonify(ok=False)
    reqs.remove(frm)
    db['friends'].setdefault(u,[]).append(frm)
    db['friends'].setdefault(frm,[]).append(u)
    save(db)
    if frm in online:
        socketio.emit('friend_accepted', {'by':u}, room=online[frm])
    return jsonify(ok=True)

@app.route('/api/friends/reject', methods=['POST'])
def reject_friend():
    u   = session.get('user')
    frm = request.json.get('from','')
    db  = load()
    reqs = db['requests'].get(u,[])
    if frm in reqs: reqs.remove(frm)
    save(db)
    return jsonify(ok=True)

@app.route('/api/profile/<username>')
def get_profile(username):
    u  = session.get('user','')
    db = load()
    user = db['users'].get(username)
    if not user: return jsonify(ok=False)
    posts   = [p for p in db['posts'] if p['author']==username][:20]
    friends = db['friends'].get(username,[])
    return jsonify(ok=True, username=username,
                   bio=user.get('bio',''), avatar=user.get('avatar',''),
                   joined=user.get('joined',''),
                   posts=posts, friends=friends,
                   friends_count=len(friends),
                   is_friend=u in friends,
                   req_sent=u in db['requests'].get(username,[]),
                   is_me=u==username)

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    u   = session.get('user')
    if not u: return jsonify(ok=False)
    d   = request.json
    db  = load()
    if 'bio' in d:    db['users'][u]['bio']    = d['bio'][:200]
    if 'avatar' in d: db['users'][u]['avatar'] = d['avatar']
    save(db)
    return jsonify(ok=True)

# ═══════════════════════════════════════
# API — الرسائل
# ═══════════════════════════════════════
def conv_key(a,b): return '|'.join(sorted([a,b]))

@app.route('/api/messages/<with_user>')
def get_messages(with_user):
    u  = session.get('user')
    if not u: return jsonify(ok=False)
    db = load()
    key  = conv_key(u, with_user)
    msgs = db['messages'].get(key,[])[-50:]
    return jsonify(ok=True, messages=msgs)

@app.route('/api/messages/<to_user>', methods=['POST'])
def send_message(to_user):
    u = session.get('user')
    if not u: return jsonify(ok=False)
    d    = request.json
    text = d.get('text','').strip()[:2000]
    if not text: return jsonify(ok=False)
    db  = load()
    key = conv_key(u, to_user)
    msg = {"from":u,"to":to_user,"text":text,"time":ts()}
    db['messages'].setdefault(key,[]).append(msg)
    db['messages'][key] = db['messages'][key][-200:]
    save(db)
    if to_user in online:
        socketio.emit('new_message', msg, room=online[to_user])
    return jsonify(ok=True, message=msg)

# ═══════════════════════════════════════
# WebSocket
# ═══════════════════════════════════════
@socketio.on('connect')
def on_connect():
    u = session.get('user')
    if u:
        online[u] = request.sid
        join_room(request.sid)
        emit('connected', {'username':u,'online':list(online.keys())})
        socketio.emit('user_online', {'username':u})

@socketio.on('disconnect')
def on_disconnect():
    u = session.get('user')
    if u and online.get(u) == request.sid:
        online.pop(u, None)
        socketio.emit('user_offline', {'username':u})

# ═══════════════════════════════════════
# الصفحة الرئيسية
# ═══════════════════════════════════════
@app.route('/')
@app.route('/<path:path>')
def index(path=''):
    return app.send_static_file('index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 djakchat يعمل على: http://localhost:{port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
