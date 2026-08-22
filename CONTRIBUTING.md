Contributing
============

If you want to contribute, you can help by [reporting
issues](https://github.com/muammar/mkchromecast/issues) or by [creating pull
requests](https://github.com/muammar/mkchromecast/pulls) with your
developments/improvements. If your case is the latter, visit
[Development](https://github.com/muammar/mkchromecast/wiki/development) section
in the Wiki.

Before opening a pull request
-----------------------------

Run the test suite; it takes under a second and the baseline is 110 passing
cases:

```
make check          # or: python -m unittest discover -s tests -v
```

`make` on its own lists the other targets, which build a wheel, a `.deb` or a
standalone binary. Note that `mkchromecast` on your PATH may belong to a
distribution package rather than to your checkout: run your changes with
`.venv/bin/python bin/mkchromecast` unless you have packaged them.

A list of contributors can be found on GitHub at
[mkchromecast/graphs/contributors](https://github.com/muammar/mkchromecast/graphs/contributors).
