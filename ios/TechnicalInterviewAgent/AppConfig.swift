import UIKit

enum AppConfig {
    static let allowedHost = "it.rainstone.top"

    static let siteURL: URL = {
        guard
            let rawValue = Bundle.main.object(
                forInfoDictionaryKey: "InterviewSiteURL"
            ) as? String,
            let url = URL(string: rawValue),
            url.scheme == "https",
            url.host?.lowercased() == allowedHost,
            url.port == nil,
            url.query == nil,
            url.fragment == nil
        else {
            preconditionFailure("InterviewSiteURL must be an approved HTTPS site.")
        }
        return url
    }()
}
