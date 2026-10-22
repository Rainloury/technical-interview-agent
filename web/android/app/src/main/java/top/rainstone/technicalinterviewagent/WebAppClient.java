package top.rainstone.technicalinterviewagent;

import android.content.Intent;
import android.net.Uri;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;

final class WebAppClient extends BridgeWebViewClient {
    private final Bridge bridge;

    WebAppClient(Bridge bridge) {
        super(bridge);
        this.bridge = bridge;
    }

    @Override
    public boolean shouldOverrideUrlLoading(@NonNull WebView view, @NonNull WebResourceRequest request) {
        Uri uri = request.getUrl();
        if (AppConfig.isSiteUri(uri)) {
            return false;
        }
        if ("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme())) {
            try {
                bridge.getActivity().startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (Exception ignored) {
                // No activity can handle the external link; keep the current app page intact.
            }
        }
        return true;
    }

    @Override
    @SuppressWarnings("deprecation")
    public boolean shouldOverrideUrlLoading(WebView view, @Nullable String url) {
        if (url == null) {
            return true;
        }
        Uri uri = Uri.parse(url);
        if (AppConfig.isSiteUri(uri)) {
            return false;
        }
        try {
            bridge.getActivity().startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (Exception ignored) {
            // No activity can handle the external link; keep the current app page intact.
        }
        return true;
    }
}
