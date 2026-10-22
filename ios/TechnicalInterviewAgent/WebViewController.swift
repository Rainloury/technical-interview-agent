import SafariServices
import UIKit
import UniformTypeIdentifiers
import WebKit

final class WebViewController: UIViewController {
    private static let allowedExternalSchemes = Set(["http", "https"])

    private let siteURL: URL
    private var webView: WKWebView!
    private var retainedDocumentPickerDelegate: UIDocumentPickerDelegate?
    private var offlineView: UIView?

    init(siteURL: URL) {
        self.siteURL = siteURL
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func loadView() {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.allowsInlineMediaPlayback = true
        configuration.mediaTypesRequiringUserActionForPlayback = [.audio, .video]
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.contentInsetAdjustmentBehavior = .automatic
        webView.scrollView.keyboardDismissMode = .interactive
        if #available(iOS 16.4, *) {
            webView.isInspectable = true
        }

        let reloadButton = UIBarButtonItem(
            image: UIImage(systemName: "arrow.clockwise"),
            style: .plain,
            target: self,
            action: #selector(reloadPage)
        )
        reloadButton.accessibilityLabel = "重新加载"
        navigationItem.rightBarButtonItem = reloadButton

        view = webView
        self.webView = webView
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        webView.load(URLRequest(url: siteURL))
    }

    @objc private func reloadPage() {
        if webView.url == nil {
            webView.load(URLRequest(url: siteURL))
        } else {
            webView.reload()
        }
    }

    private func showOfflineState() {
        guard offlineView == nil else {
            return
        }

        let title = UILabel()
        title.text = "无法连接"
        title.font = .preferredFont(forTextStyle: .title2)
        title.textAlignment = .center

        let detail = UILabel()
        detail.text = "请检查网络后重试。"
        detail.font = .preferredFont(forTextStyle: .body)
        detail.textColor = .secondaryLabel
        detail.textAlignment = .center
        detail.numberOfLines = 0

        var buttonConfiguration = UIButton.Configuration.filled()
        buttonConfiguration.title = "重新加载"
        let button = UIButton(configuration: buttonConfiguration)
        button.addTarget(self, action: #selector(reloadPage), for: .touchUpInside)

        let stack = UIStackView(arrangedSubviews: [title, detail, button])
        stack.axis = .vertical
        stack.alignment = .center
        stack.spacing = 12
        stack.isLayoutMarginsRelativeArrangement = true
        stack.layoutMargins = UIEdgeInsets(top: 24, left: 24, bottom: 24, right: 24)
        stack.translatesAutoresizingMaskIntoConstraints = false

        let offline = UIView()
        offline.backgroundColor = .systemBackground
        offline.translatesAutoresizingMaskIntoConstraints = false
        offline.addSubview(stack)
        view.addSubview(offline)
        constraintsForOfflineView(offline, content: stack)
        offlineView = offline
    }

    private func hideOfflineState() {
        offlineView?.removeFromSuperview()
        offlineView = nil
    }

    private func constraintsForOfflineView(_ offline: UIView, content: UIView) {
        NSLayoutConstraint.activate([
            offline.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            offline.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            offline.topAnchor.constraint(equalTo: view.topAnchor),
            offline.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            content.centerXAnchor.constraint(equalTo: offline.centerXAnchor),
            content.centerYAnchor.constraint(equalTo: offline.centerYAnchor),
            content.leadingAnchor.constraint(
                greaterThanOrEqualTo: offline.leadingAnchor,
                constant: 24
            ),
            content.trailingAnchor.constraint(
                lessThanOrEqualTo: offline.trailingAnchor,
                constant: -24
            ),
        ])
    }

    private func presentSystemBrowser(for url: URL) {
        guard Self.allowedExternalSchemes.contains(url.scheme?.lowercased() ?? "") else {
            return
        }
        let browser = SFSafariViewController(url: url)
        browser.dismissButtonStyle = .close
        present(browser, animated: true)
    }
}

extension WebViewController: WKNavigationDelegate {
    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.cancel)
            return
        }

        let isInternalHost = url.host?.lowercased() == siteURL.host?.lowercased()
        let isMainFrame = navigationAction.targetFrame?.isMainFrame ?? false

        if isInternalHost {
            decisionHandler(.allow)
            return
        }

        if navigationAction.navigationType == .linkActivated || !isMainFrame {
            decisionHandler(.cancel)
            presentSystemBrowser(for: url)
            return
        }

        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        hideOfflineState()
    }

    func webView(
        _ webView: WKWebView,
        didFail navigation: WKNavigation!,
        withError error: Error
    ) {
        guard (error as NSError).code != NSURLErrorCancelled else {
            return
        }
        showOfflineState()
    }

    func webView(
        _ webView: WKWebView,
        didFailProvisionalNavigation navigation: WKNavigation!,
        withError error: Error
    ) {
        guard (error as NSError).code != NSURLErrorCancelled else {
            return
        }
        showOfflineState()
    }
}

extension WebViewController: WKUIDelegate {
    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping ([URL]?) -> Void
    ) {
        var contentTypes: [UTType] = [.pdf, .plainText]
        if let docx = UTType(
            "org.openxmlformats.wordprocessingml.document"
        ) {
            contentTypes.append(docx)
        }
        if let markdown = UTType("net.daringfireball.markdown") {
            contentTypes.append(markdown)
        }

        let picker = UIDocumentPickerViewController(
            forOpeningContentTypes: contentTypes,
            asCopy: true
        )
        picker.allowsMultipleSelection = parameters.allowsMultipleSelection
        let delegate = DocumentPickerDelegate(
            completionHandler: completionHandler,
            presentingViewController: self
        )
        picker.delegate = delegate
        retainedDocumentPickerDelegate = delegate
        present(picker, animated: true)
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptAlertPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping () -> Void
    ) {
        guard presentedViewController == nil else {
            completionHandler()
            return
        }
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "好", style: .default) { _ in
            completionHandler()
        })
        present(alert, animated: true)
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptConfirmPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping (Bool) -> Void
    ) {
        guard presentedViewController == nil else {
            completionHandler(false)
            return
        }
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in
            completionHandler(false)
        })
        alert.addAction(UIAlertAction(title: "确认", style: .default) { _ in
            completionHandler(true)
        })
        present(alert, animated: true)
    }

    func webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if let url = navigationAction.request.url {
            presentSystemBrowser(for: url)
        }
        return nil
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptTextInputPanelWithPrompt prompt: String,
        defaultText: String?,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping (String?) -> Void
    ) {
        guard presentedViewController == nil else {
            completionHandler(nil)
            return
        }
        let alert = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        alert.addTextField { textField in
            textField.text = defaultText
        }
        alert.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in
            completionHandler(nil)
        })
        alert.addAction(UIAlertAction(title: "确认", style: .default) { _ in
            completionHandler(alert.textFields?.first?.text)
        })
        present(alert, animated: true)
    }
}

private final class DocumentPickerDelegate: NSObject, UIDocumentPickerDelegate {
    private let completionHandler: ([URL]?) -> Void
    private weak var presentingViewController: UIViewController?

    init(
        completionHandler: @escaping ([URL]?) -> Void,
        presentingViewController: UIViewController
    ) {
        self.completionHandler = completionHandler
        self.presentingViewController = presentingViewController
    }

    func documentPicker(
        _ controller: UIDocumentPickerViewController,
        didPickDocumentsAt urls: [URL]
    ) {
        completionHandler(urls)
        presentingViewController?.dismiss(animated: true)
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        completionHandler(nil)
        presentingViewController?.dismiss(animated: true)
    }
}
