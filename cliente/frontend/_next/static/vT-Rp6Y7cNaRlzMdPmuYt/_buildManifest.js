self.__BUILD_MANIFEST = {
  "__rewrites": {
    "afterFiles": [
      {
        "source": "/auth/:path*"
      },
      {
        "source": "/users/:path*"
      },
      {
        "source": "/user/:path*"
      },
      {
        "source": "/dashboard/:path*"
      },
      {
        "source": "/broker/:path*"
      },
      {
        "source": "/copier/:path*"
      },
      {
        "source": "/telegram/:path*"
      },
      {
        "source": "/stats/:path*"
      },
      {
        "source": "/admin/:path*"
      },
      {
        "source": "/signal"
      },
      {
        "source": "/create-checkout-session"
      },
      {
        "source": "/account/:path*"
      },
      {
        "source": "/version"
      },
      {
        "source": "/api/:path*"
      },
      {
        "source": "/mt4/:path*"
      },
      {
        "source": "/risk-term/:path*"
      },
      {
        "source": "/planilha/:path*"
      }
    ],
    "beforeFiles": [],
    "fallback": []
  },
  "sortedPages": [
    "/_app",
    "/_error"
  ]
};self.__BUILD_MANIFEST_CB && self.__BUILD_MANIFEST_CB()