self.__BUILD_MANIFEST = {
  "__rewrites": {
    "afterFiles": [
      {
        "source": "/",
        "destination": "/pages?view=home"
      },
      {
        "source": "/admin",
        "destination": "/pages?view=admin"
      },
      {
        "source": "/department-head",
        "destination": "/pages?view=department-head"
      },
      {
        "source": "/professor",
        "destination": "/pages?view=professor"
      },
      {
        "source": "/student",
        "destination": "/pages?view=student"
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