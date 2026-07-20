window.HANKO_DOWNLOAD_CONFIG = {
  fallbackPlatform: "mac",
  platforms: {
    mac: {
      enabled: true,
      label: "Mac版をダウンロード",
      url: "https://github.com/yupyom/hanko-pdf/releases/latest"
    },
    windows: {
      enabled: true,
      label: "Microsoft Storeから入手",
      url: "https://apps.microsoft.com/detail/9P6SK13W5K4F",
      badge: {
        href: "https://get.microsoft.com/installer/download/9P6SK13W5K4F?referrer=appbadge",
        image: "https://get.microsoft.com/images/ja%20light.svg",
        alt: "Microsoftから入手",
        width: 200
      }
    },
    linux: {
      enabled: false,
      label: "Linux版をダウンロード",
      url: "https://github.com/yupyom/hanko-pdf/releases/latest"
    }
  }
};
