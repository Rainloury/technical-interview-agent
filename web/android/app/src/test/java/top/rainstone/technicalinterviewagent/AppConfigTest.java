package top.rainstone.technicalinterviewagent;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class AppConfigTest {
    @Test
    public void acceptsOnlyTheProductionHttpsOrigin() {
        assertTrue(AppConfig.isSiteUrl("https://it.rainstone.top/login"));
        assertTrue(AppConfig.isSiteUrl("https://IT.RAINSTONE.TOP:443/login"));
        assertFalse(AppConfig.isSiteUrl("http://it.rainstone.top/login"));
        assertFalse(AppConfig.isSiteUrl("https://example.com/login"));
        assertFalse(AppConfig.isSiteUrl(null));
    }

    @Test
    public void preservesDeepLinkPathAndQuery() {
        assertEquals(
            "https://it.rainstone.top/reset-password?token=one%20two",
            AppConfig.siteUrlForPath("https://it.rainstone.top/reset-password?token=one%20two")
        );
    }

    @Test
    public void rejectsDeepLinksThatCannotBeLoadedInTheApp() {
        assertEquals(
            "https://it.rainstone.top/",
            AppConfig.siteUrlForPath("https://example.com/login")
        );
        assertEquals(
            "https://it.rainstone.top/",
            AppConfig.siteUrlForPath(null)
        );
    }
}
