package lab.tv.share;
import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.TextView;
import java.io.*;

/** Visible companion to the Mac viewer; it captures no screen or audio itself. */
public class ShareService extends Service {
    private WindowManager manager;
    private TextView badge;
    private File active, stop;
    private String token;
    private int dp(int value) { return Math.round(getResources().getDisplayMetrics().density * value); }
    public void onCreate() {
        super.onCreate();
        File dir = getExternalFilesDir(null);
        if (dir != null) { active = new File(dir, "active"); stop = new File(dir, "stop"); }
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel("sharing", "Active screen sharing", NotificationManager.IMPORTANCE_LOW));
        PendingIntent requestStop = PendingIntent.getService(this, 0,
                new Intent(this, ShareService.class).setAction("STOP"), PendingIntent.FLAG_IMMUTABLE);
        PendingIntent panel = PendingIntent.getActivity(this, 0,
                new Intent(this, ShareActivity.class), PendingIntent.FLAG_IMMUTABLE);
        startForeground(1, new Notification.Builder(this, "sharing")
                .setSmallIcon(android.R.drawable.ic_menu_view).setContentTitle("Screen sharing with Mac")
                .setContentText("The TV screen is visible on the connected Mac.").setOngoing(true)
                .setContentIntent(panel).addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop sharing", requestStop).build());
    }
    public int onStartCommand(Intent intent, int flags, int id) {
        String action = intent == null ? null : intent.getAction();
        if ("END".equals(action)) { stopSelf(); return START_NOT_STICKY; }
        if ("STOP".equals(action)) {
            try { if (stop != null) new FileOutputStream(stop).close(); } catch (IOException ignored) {}
            if (badge != null) badge.setText("● Stopping screen sharing…");
            return START_NOT_STICKY;
        }
        if (!Settings.canDrawOverlays(this) || active == null) { stopSelf(); return START_NOT_STICKY; }
        String next = intent == null ? null : intent.getStringExtra("session");
        if (next == null || next.isEmpty()) { if (badge == null) stopSelf(); return START_NOT_STICKY; }
        try {
            if (badge == null) {
                manager = (WindowManager)getSystemService(WINDOW_SERVICE);
                badge = new TextView(this); badge.setText("● Screen sharing · Mac"); badge.setTextColor(Color.WHITE);
                badge.setTextSize(13); badge.setPadding(dp(12),dp(7),dp(12),dp(7));
                GradientDrawable bg = new GradientDrawable(); bg.setColor(0xed28394b);bg.setCornerRadius(dp(8));badge.setBackground(bg);
                WindowManager.LayoutParams p = new WindowManager.LayoutParams(-2,-2,
                        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
                        PixelFormat.TRANSLUCENT);
                p.gravity=Gravity.TOP|Gravity.RIGHT;p.x=dp(16);p.y=dp(14);
                manager.addView(badge,p);
            }
            token=next;
            if (stop.exists()) stop.delete();
            try(FileOutputStream out=new FileOutputStream(active)){out.write(token.getBytes("UTF-8"));}
        } catch (Exception error) { stopSelf(); }
        return START_NOT_STICKY;
    }
    public void onDestroy(){
        if(active!=null)active.delete(); if(stop!=null)stop.delete();
        if(manager!=null&&badge!=null)try{manager.removeView(badge);}catch(Exception ignored){}
        stopForeground(true);super.onDestroy();
    }
    public IBinder onBind(Intent i){return null;}
}
