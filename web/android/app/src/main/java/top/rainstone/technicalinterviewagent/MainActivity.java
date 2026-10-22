package top.rainstone.technicalinterviewagent;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        CookieManager.getInstance().setAcceptCookie(true);
        super.onCreate(savedInstanceState);
        WebView webView = getBridge().getWebView();
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false);
        webView.getSettings().setAllowFileAccess(false);
        webView.getSettings().setAllowContentAccess(false);
        webView.getSettings().setDomStorageEnabled(true);
        getBridge().setWebViewClient(new WebAppClient(getBridge()));
        loadDeepLink(getIntent().getData());
    }

    @Override
    public void onResume() {
        super.onResume();
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        Uri uri = intent.getData();
        if (uri == null) {
            return;
        }
        setIntent(intent);
        loadDeepLink(uri);
    }

    private void loadDeepLink(Uri uri) {
        if (AppConfig.isSiteUri(uri) && uri.getPath() != null && !uri.getPath().isEmpty() && !"/".equals(uri.getPath())) {
            getBridge().getWebView().loadUrl(AppConfig.siteUrlForIntent(uri));
        }
    }
}
