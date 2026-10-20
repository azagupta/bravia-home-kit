package lab.tv.sky;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ComponentName;
import android.content.Intent;
import android.media.tv.TvContract;
import android.media.tv.TvInputInfo;
import android.media.tv.TvInputManager;
import android.os.Bundle;
import android.util.Log;
import android.widget.Toast;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

/** Resolves the live HDMI inventory on every launch. Never assumes a fixed port. */
public class SkyActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        try {
            TvInputManager manager = (TvInputManager) getSystemService(TV_INPUT_SERVICE);
            if (manager == null) { fail("TV input information unavailable. Use the remote’s Input button."); return; }
            List<TvInputInfo> all = manager.getTvInputList();
            List<TvInputInfo> connected = new ArrayList<>();
            List<TvInputInfo> namedSky = new ArrayList<>();
            for (TvInputInfo input : all) {
                if (input.getType() != TvInputInfo.TYPE_HDMI
                        || manager.getInputState(input.getId()) != TvInputManager.INPUT_STATE_CONNECTED) continue;
                if (isSky(input)) namedSky.add(input);
                // CEC devices are children of a physical port, not additional HDMI sockets.
                if (input.getParentId() == null) connected.add(input);
            }
            if (namedSky.size() == 1) { tune(namedSky.get(0)); return; }
            if (namedSky.isEmpty() && connected.size() == 1) { tune(connected.get(0)); return; }
            List<TvInputInfo> choices = namedSky.isEmpty() ? connected : namedSky;
            if (choices.isEmpty()) { fail("No active HDMI input found. Turn on Sky, then open this tile again."); return; }
            Collections.sort(choices, (a, b) -> label(a).compareToIgnoreCase(label(b)));
            String[] labels = new String[choices.size()];
            for (int i = 0; i < choices.size(); i++) labels[i] = label(choices.get(i));
            new AlertDialog.Builder(this).setTitle("Which input is Sky?")
                    .setItems(labels, (dialog, which) -> tune(choices.get(which)))
                    .setNegativeButton("Cancel", (dialog, which) -> finish())
                    .setOnCancelListener(dialog -> finish()).show();
        } catch (RuntimeException error) {
            Log.e("SkyShortcut", "Cannot read HDMI inventory", error);
            fail("Could not detect Sky. Use the remote’s Input button.");
        }
    }
    private String label(TvInputInfo input) {
        CharSequence custom = input.loadCustomLabel(this);
        CharSequence original = input.loadLabel(this);
        String base = original == null ? "HDMI" : original.toString();
        return custom == null || custom.length() == 0 ? base : custom + " · " + base;
    }
    private boolean isSky(TvInputInfo input) {
        return java.util.regex.Pattern.compile("\\bsky(?:\\s*(?:q|stream|glass|hd))?\\b")
                .matcher(label(input).toLowerCase(Locale.ROOT)).find();
    }
    private void tune(TvInputInfo input) {
        try {
            Log.i("SkyShortcut", "Opening " + input.getId() + " (" + label(input) + ")");
            Intent intent = new Intent(Intent.ACTION_VIEW).setDataAndType(
                    TvContract.buildChannelUriForPassthroughInput(input.getId()), "vnd.android.cursor.item/channel")
                    .setComponent(new ComponentName("com.sony.dtv.tvx", "com.sony.dtv.tvx.MainActivity"));
            startActivity(intent);
            finish();
        } catch (RuntimeException error) {
            Log.e("SkyShortcut", "Cannot open input", error);
            fail("Could not open Sky. Use the remote’s Input button.");
        }
    }
    private void fail(String message) { Toast.makeText(this, message, Toast.LENGTH_LONG).show(); finish(); }
}
