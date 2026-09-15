#!/usr/bin/env python3
"""Update the battery for v11.4 (reveals, top3, tomorrow plan, no paid message, iari 3 pages)."""
p = "tests/fake_clock.py"
s = open(p).read()
n0 = len(s)

# ---- case 2 (malwa 20Q)
s = s.replace('''    tmr = [t for t in texts(log) if t.startswith("📖 Tomorrow")]
    ann_id = day_of(st, day, "malwa").get("msg_ann")''',
'''    tmr = [t for t in texts(log) if t.startswith("🗓")]
    reveals = [t for t in texts(log) if t.startswith("✅ <b>Q")]
    toppers = [t for t in texts(log) if "TOP 3" in t]
    paid_msgs = [t for t in texts(log) if "PAID BATCHES" in t]
    ann_id = day_of(st, day, "malwa").get("msg_ann")''')
s = s.replace('''    paid_msgs = [t for t in texts(log) if "PAID BATCHES" in t]
    kb = [e for e in methods(log, "sendMessage", GROUP) if e.get("reply_markup")]''',
'''    kb = [e for e in methods(log, "sendMessage", GROUP) if e.get("reply_markup")]''')
s = s.replace('''    ok = (len(ann) == 1 and len(pl) == 20 and all(e.get("open_period") == 30 for e in pl)
          and all(e["question"].startswith("%d/20." % (i + 1)) for i, e in enumerate(pl))
          and len(pin_calls) == 1 and pin_calls[0]["message_id"] == ann_id          # announce is the ONLY pin
          and "Book pages" in ann[0] and len(tmr) == 1 and "Tomorrow" in tmr[0]      # pages line + tomorrow note
          and lb and texts(log).index(ann[0]) < texts(log).index(lb[0]) < texts(log).index(tmr[0])
          and len(lb) == 1 and len(docs) == 1 and len(cta) == 1
          and cd_vals and max(cd_vals) == 15 and len(cd_vals) >= 4          # v11.1: single 15s countdown
          and len(paid_msgs) == 1 and "PAID BATCHES" in (last_group_msg.get("text") or "")  # paid = LAST
          and kb and len(kb[-1]["reply_markup"]["inline_keyboard"]) >= 4
          and not hinglish and int(j.get("step", 0)) == 8
          and int(day_of(st, day, "iari").get("step", 0)) == 0)''',
'''    idx = texts(log)
    ok = (len(ann) == 1 and len(pl) == 20 and all(e.get("open_period") == 30 for e in pl)
          and all(e["question"].startswith("%d/20." % (i + 1)) for i, e in enumerate(pl))
          and len(pin_calls) == 1 and pin_calls[0]["message_id"] == ann_id          # announce is the ONLY pin
          and "Book pages" in ann[0]
          and len(reveals) == 20 and "📖" in reveals[0]                              # reveal + explanation each Q
          and len(lb) == 1 and len(toppers) == 1 and len(docs) == 1 and len(tmr) == 1 and len(cta) == 1
          and idx.index(ann[0]) < idx.index(lb[0]) < idx.index(toppers[0])           # ... < top3
          and idx.index(toppers[0]) < idx.index(cta[0]) and idx.index(tmr[0]) < idx.index(cta[0])
          and len(paid_msgs) == 0 and not kb                                         # paid message OFF
          and cd_vals and max(cd_vals) == 15 and len(cd_vals) >= 4
          and not hinglish and int(j.get("step", 0)) == 8
          and int(day_of(st, day, "iari").get("step", 0)) == 0)
    _ = last_group_msg''')
s = s.replace('''    return ok, ("announce=%d polls=%d ticks=%s pins=%d(only announce=%s) unpins=%d lb=%d tomorrow=%r docs=%d "
                "cta=%d paid_last=%s buttons=%d hinglish=%d step=%s" % (
                    len(ann), len(pl), cd_vals, len(pin_calls),
                    bool(pin_calls) and pin_calls[0]["message_id"] == ann_id, len(unpins), len(lb),
                    (tmr[0][:42] if tmr else None), len(docs), len(cta),
                    "PAID BATCHES" in (last_group_msg.get("text") or ""),
                    len(kb[-1]["reply_markup"]["inline_keyboard"]) if kb else 0, len(hinglish), j.get("step")))''',
'''    return ok, ("announce=%d polls=%d reveals=%d ticks=%s pins=%d unpins=%d lb=%d top3=%d docs=%d plan=%r "
                "cta=%d paid=%d hinglish=%d step=%s" % (
                    len(ann), len(pl), len(reveals), cd_vals, len(pin_calls), len(unpins), len(lb),
                    len(toppers), len(docs), (tmr[0][:40] if tmr else None), len(cta), len(paid_msgs),
                    len(hinglish), j.get("step")))''')

# ---- case 3
s = s.replace('''          and int(day_of(st2, day, "iari").get("step", 0)) == 8 and len(pl2) == 15''',
'''          and int(day_of(st2, day, "iari").get("step", 0)) == 8 and len(pl2) == 8    # 3 pages = 3+3+2 Q''')
s = s.replace('''    return ok, ("cycle1: announces=%d polls=%d malwa=%s iari=%s(deferred) | cycle2: iari polls=%d iari.step=%s"''',
'''    return ok, ("cycle1: announces=%d polls=%d malwa=%s iari=%s(deferred) | cycle2: iari polls=%d (3 pages) iari.step=%s"''')

# ---- case 9
s = s.replace('''    tmr = [t for t in texts(log) if t.startswith("📖 Tomorrow")]
    pin_calls = pins(log)''',
'''    tmr = [t for t in texts(log) if t.startswith("🗓")]
    reveals = [t for t in texts(log) if t.startswith("✅ <b>Q")]
    pin_calls = pins(log)''')
s = s.replace('''          and len(iann) == 1 and "Book pages: 2, 4, 5, 7, 8" in iann[0]      # iari pages listed exactly
          and len(tmr) == 2 and any("9, 10" in t for t in tmr)              # iari tomorrow = pages 9, 10
          and int(m.get("step", 0)) == 8 and len(pl) == 35
          and iari_q and (i.get("plan") or {}).get("pages_list") == [2, 4, 5, 7, 8]''',
'''          and len(iann) == 1 and "Book pages: 2, 4, 5" in iann[0]            # 3 pages/day (v11.4)
          and len(tmr) == 2 and any("7, 8, 9" in t for t in tmr)             # tomorrow = next 3 pages
          and int(m.get("step", 0)) == 8 and len(pl) == 28                   # 20 malwa + 8 iari
          and len(reveals) == 28
          and iari_q and (i.get("plan") or {}).get("pages_list") == [2, 4, 5]''')
s = s.replace('''    return ok, "iari.step=%s malwa.step=%s polls=%d iari_pages=%s pins=%s unpinned=%s tomorrow=%d ticks(max %s)" % (
        i.get("step"), m.get("step"), len(pl), (i.get("plan") or {}).get("pages_list"),
        [x["message_id"] for x in pin_calls], [x["message_id"] for x in unp], len(tmr), max(cd) if cd else None)''',
'''    return ok, ("iari.step=%s malwa.step=%s polls=%d reveals=%d iari_pages=%s pins=%s unpinned=%s plan=%d "
                "ticks(max %s)" % (i.get("step"), m.get("step"), len(pl), len(reveals),
                                   (i.get("plan") or {}).get("pages_list"),
                                   [x["message_id"] for x in pin_calls], [x["message_id"] for x in unp],
                                   len(tmr), max(cd) if cd else None))''')

# ---- case 10 (AFO)
s = s.replace('''          and len(aann) == 1 and "Book pages" not in aann[0]
          and not [t for t in texts(log) if t.startswith("📖 Tomorrow")])''',
'''          and len(aann) == 1 and "Book pages" not in aann[0]
          and len([t for t in texts(log) if t.startswith("🗓")]) == 1
          and len([t for t in texts(log) if "🌆 6:00 PM" in t]) == 1)''')

# ---- case 16
s = s.replace('''    ok = (len(pinz) == 1 and pinz[0]["message_id"] == i.get("msg_ann")
          and len(unp) == 1 and unp[0]["message_id"] == 777 and i.get("unpinned") == [777])''',
'''    ok = (len(pinz) == 1 and pinz[0]["message_id"] == i.get("msg_ann")
          and len(unp) == 1 and unp[0]["message_id"] == 777 and i.get("unpinned") == [777]
          and not [t for t in texts(log) if "PAID BATCHES" in t])''')

open(p, "w").write(s)
print("battery updated for v11.4 (%d -> %d chars)" % (n0, len(s)))
