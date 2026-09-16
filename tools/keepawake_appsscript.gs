/**
 * AGRI QUIZ DAILY EXAM SYSTEM — free keep-awake pinger (Google Apps Script)
 * ---------------------------------------------------------------------------
 * WHY: Render's free web service sleeps after 15 minutes without traffic, and
 *      GitHub's cron on this account is not firing. Apps Script runs on your
 *      own Google account (the same one that owns the quiz sheets) — free,
 *      no card, no GitHub minutes.
 *
 * SETUP (2 minutes, once):
 *   1. Open  https://script.google.com  ->  New project
 *   2. Delete the sample code, paste this whole file, save (name it "agri-keepawake").
 *   3. Click  Run  once and allow permissions when Google asks
 *      (choose your own account -> Advanced -> Go to agri-keepawake (unsafe) -> Allow).
 *   4. Left menu  Triggers (clock icon)  ->  Add trigger:
 *        Function: keepAwake
 *        Event source: Time-driven
 *        Type: Minutes timer
 *        Interval: Every 5 minutes
 *      Save. Done — it now pings the runner 24x7.
 *   5. (Optional) Executions tab shows the log: ping=200 cycles=... errors=none
 */

const RUNNER = 'https://live-test-8wu1.onrender.com';
const ADMIN_KEY = ''; // optional: paste the ADMIN_KEY only if you also want /run/status checks

function keepAwake() {
  const t0 = Date.now();
  try {
    const ping = UrlFetchApp.fetch(RUNNER + '/ping', { muteHttpExceptions: true, followRedirects: true });
    const code = ping.getResponseCode();
    let line = '';
    try {
      const st = JSON.parse(UrlFetchApp.fetch(RUNNER + '/', { muteHttpExceptions: true }).getContentText());
      let next = '';
      (st.next_slots || []).slice(0, 3).forEach(function (s) {
        next += s.slot + '(+' + s.in_minutes + 'm) ';
      });
      line = 'cycles=' + JSON.stringify(st.cycles) +
             ' last=' + JSON.stringify(st.last || {}).slice(0, 140) +
             ' errors=' + JSON.stringify(st.last_error || {}) +
             ' next=' + next;
    } catch (e) {
      line = 'status page unreadable: ' + e;
    }
    console.log(new Date().toISOString() + '  /ping=' + code + '  ' + line + '  (' + (Date.now() - t0) + ' ms)');
    if (code !== 200) {
      console.warn('runner not healthy — HTTP ' + code + '. It may be cold-starting (Render wakes in ~30-60 s); the next ping will confirm.');
    }
  } catch (err) {
    console.error('ping failed: ' + err);
  }
}

/** Optional: sends you a Telegram DM if the runner is down. Needs a bot token + your chat id. */
function keepAwakeWithAlert() {
  keepAwake();
  try {
    const st = JSON.parse(UrlFetchApp.fetch(RUNNER + '/', { muteHttpExceptions: true }).getContentText());
    const errs = st.last_error && Object.keys(st.last_error).length;
    const last = st.last || {};
    const stale = last.slotchain ? (Date.now() - new Date(last.slotchain.at).getTime()) / 60000 : 999;
    if (errs || stale > 45) {
      // Silent guard: only complain during test hours (10:00-20:00 IST)
      const ist = new Date(Date.now() + 5.5 * 3600 * 1000);
      const h = ist.getUTCHours();
      if (h >= 10 && h < 20) {
        console.warn('GUARD: errors=' + errs + ' slotchain last ran ' + Math.round(stale) + ' min ago — check the Render log');
      }
    }
  } catch (e) {}
}
