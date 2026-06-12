// Pre-paint theme bootstrap. Kept as an external file (not an inline <script>)
// so the app's Content-Security-Policy can drop 'unsafe-inline' from script-src.
// Loaded as a blocking script in <head> so the theme class is applied before
// first paint (no flash of the wrong theme).
(function () {
  var theme = localStorage.getItem('sublarr-theme')
  if (theme === 'light') {
    document.documentElement.classList.remove('dark')
  } else if (theme === 'dark' || !theme) {
    document.documentElement.classList.add('dark')
  } else {
    // system
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.classList.add('dark')
    }
  }
})()
