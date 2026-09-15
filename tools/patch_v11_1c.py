#!/usr/bin/env python3
"""One-shot patch part 3: offline test doubles for the paid/enrolment flow + `ready` invite-rights check."""
import sys

P = "engine/engine.py"
s = open(P, encoding="utf-8").read()

# ---------- 1. fake telegram: injectable updates + paid methods ----------
OLD_UPD = '''def _fake_updates(params):
    """Synthetic poll_answer updates for the last poll (two players: one right, one wrong)."""
    pid = _last_poll.get("id")
    if not pid or params.get("offset") in (None, -1):
        return []
    users = [("9001", "TestAlpha", 0), ("9002", "TestBeta", 1)]
    return [{"update_id": _fake_ids[0] + 10 + i, "poll_answer": {
        "poll_id": pid, "user": {"id": int(u), "first_name": n, "username": None}, "option_ids": [o]}}
        for i, (u, n, o) in enumerate(users)]'''
NEW_UPD = '''_injected = {"served": False}


def _fake_updates(params):
    """Updates for the offline battery.
    ENGINE_FAKE_UPDATES=<json file> injects real update objects once (desk/enrolment tests);
    otherwise poll_answer updates are synthesised for the last poll (two players: one right, one wrong)."""
    if os.environ.get("ENGINE_FAKE_UPDATES"):
        if _injected["served"]:
            return []
        _injected["served"] = True
        try:
            ups = json.load(open(os.environ["ENGINE_FAKE_UPDATES"], encoding="utf-8"))
        except Exception:
            return []
        off = params.get("offset") or 0
        try:
            off = int(off)
        except Exception:
            off = 0
        return [u for u in ups if int(u.get("update_id", 0)) >= max(off, 0)]
    pid = _last_poll.get("id")
    if not pid or params.get("offset") in (None, -1):
        return []
    users = [("9001", "TestAlpha", 0), ("9002", "TestBeta", 1)]
    return [{"update_id": _fake_ids[0] + 10 + i, "poll_answer": {
        "poll_id": pid, "user": {"id": int(u), "first_name": n, "username": None}, "option_ids": [o]}}
        for i, (u, n, o) in enumerate(users)]'''
s = s.replace(OLD_UPD, NEW_UPD, 1)

OLD_LOG = '''    entry = {"t": istnow().isoformat(timespec="seconds"), "method": method,
             "chat": str(params.get("chat_id") or ""), "message_id": params.get("message_id"),
             "text": params.get("text"), "caption": params.get("caption"), "question": params.get("question"),
             "options": params.get("options"), "open_period": params.get("open_period")}'''
NEW_LOG = '''    entry = {"t": istnow().isoformat(timespec="seconds"), "method": method,
             "chat": str(params.get("chat_id") or ""), "message_id": params.get("message_id"),
             "text": params.get("text"), "caption": params.get("caption"), "question": params.get("question"),
             "options": params.get("options"), "open_period": params.get("open_period"),
             "reply_markup": params.get("reply_markup"), "member_limit": params.get("member_limit"),
             "payload": params.get("payload"), "data": params.get("data")}'''
s = s.replace(OLD_LOG, NEW_LOG, 1)

OLD_MEMBER = '''    if method == "getChatMember":
        return {"status": FAKE_MEMBER, "can_pin_messages": FAKE_MEMBER in ("administrator", "creator"),
                "can_delete_messages": FAKE_MEMBER in ("administrator", "creator"),
                "user": {"id": 8585018636, "is_bot": True, "username": "Arunkatyanquiz_bot"}}'''
NEW_MEMBER = '''    if method == "getChatMember":
        admin = FAKE_MEMBER in ("administrator", "creator")
        return {"status": FAKE_MEMBER, "can_pin_messages": admin, "can_delete_messages": admin,
                "can_invite_users": admin,
                "user": {"id": 8585018636, "is_bot": True, "username": "Arunkatyanquiz_bot"}}'''
s = s.replace(OLD_MEMBER, NEW_MEMBER, 1)

OLD_RES = '''    if method in ("editMessageText", "editMessageCaption", "pinChatMessage", "unpinChatMessage",
                  "deleteMessage", "sendChatAction"):
        return {"message_id": params.get("message_id"), "ok_": True}
    return {"ok_": True}'''
NEW_RES = '''    if method == "createChatInviteLink":
        _fake_ids[0] += 1
        return {"invite_link": "https://t.me/+FAKE%06d" % _fake_ids[0], "name": params.get("name"),
                "member_limit": params.get("member_limit"), "creates_join_request": False}
    if method == "sendInvoice":
        _fake_ids[0] += 1
        return {"message_id": _fake_ids[0]}
    if method in ("editMessageText", "editMessageCaption", "pinChatMessage", "unpinChatMessage",
                  "deleteMessage", "sendChatAction", "answerCallbackQuery", "editMessageReplyMarkup",
                  "approveChatJoinRequest", "declineChatJoinRequest", "revokeChatInviteLink"):
        return {"message_id": params.get("message_id"), "ok_": True}
    return {"ok_": True}'''
s = s.replace(OLD_RES, NEW_RES, 1)

# ---------- 2. ready(): also check invite rights per paid batch group ----------
OLD_READY = '''def ready():
    ok, can_pin, why = can_post(CHAT)
    b = tg("getMe") or {}
    print("GATE0 chat=%s bot=@%s can_post=%s can_pin=%s reason=%s" % (CHAT, b.get("username"), ok, can_pin, why))
    return 0 if ok else 3'''
NEW_READY = '''def ready():
    ok, can_pin, why = can_post(CHAT)
    b = tg("getMe") or {}
    print("GATE0 chat=%s bot=@%s can_post=%s can_pin=%s reason=%s" % (CHAT, b.get("username"), ok, can_pin, why))
    SELF = sys.modules[__name__]
    bad = 0
    for bt in paid.batches():
        iok, status = paid.invite_ok(SELF, bt["chat"])
        if not iok:
            bad += 1
        print("  batch %-6s chat=%s invite_rights=%-5s (bot status=%s)" % (bt["key"], bt["chat"], iok, status))
    if bad:
        print("  NOTE: %d batch group(s) need @Arunkatyanquiz_bot as admin with the Invite Users right" % bad)
    return 0 if ok else 3'''
s = s.replace(OLD_READY, NEW_READY, 1)

open(P, "w", encoding="utf-8").write(s)
print("part 3 ok: fake doubles + ready() invite check")
