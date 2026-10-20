package lab.tv.share;
public class ShareActivity extends android.app.Activity {
 public void onCreate(android.os.Bundle b){super.onCreate(b);
  java.io.File dir=getExternalFilesDir(null);
  boolean active=dir!=null&&new java.io.File(dir,"active").exists();
  android.app.AlertDialog.Builder panel=new android.app.AlertDialog.Builder(this).setTitle("Screen sharing")
    .setMessage(active?"This TV’s screen is being shared with the connected Mac. You can stop sharing here.":"Screen sharing is off. Start it using TV Screen Share on your Mac.")
    .setNegativeButton("Close",(d,w)->finish()).setOnCancelListener(d->finish());
  if(active)panel.setPositiveButton("Stop sharing",(d,w)->{startService(new android.content.Intent(this,ShareService.class).setAction("STOP"));finish();});
  panel.show();
 }
}
