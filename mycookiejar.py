import time, re, io
from cookielib import (_warn_unhandled_exception, LWPCookieJar, LoadError,
                       Cookie, MISSING_FILENAME_TEXT,
                       join_header_words, split_header_words,
                       iso2time, time2isoz)

def lwp_cookie_str(cookie):
    """Return string representation of Cookie in an the LWP cookie file format.

    Actually, the format is extended a bit -- see module docstring.

    """
    # force max 32bit signed value
    if cookie.expires > 2147483647:
        print "Forcing 32bit cookie expiration date"
        cookie.expires = 2147483647
    
    h = [(cookie.name, cookie.value),
         ("path", cookie.path),
         ("domain", cookie.domain)]
    if cookie.port is not None: h.append(("port", cookie.port))
    if cookie.path_specified: h.append(("path_spec", None))
    if cookie.port_specified: h.append(("port_spec", None))
    if cookie.domain_initial_dot: h.append(("domain_dot", None))
    if cookie.secure: h.append(("secure", None))
    if cookie.expires: h.append(("expires",
                               time2isoz(float(cookie.expires))))
    if cookie.discard: h.append(("discard", None))
    if cookie.comment: h.append(("comment", cookie.comment))
    if cookie.comment_url: h.append(("commenturl", cookie.comment_url))

    keys = cookie._rest.keys()
    keys.sort()
    for k in keys:
        h.append((k, str(cookie._rest[k])))

    h.append(("version", str(cookie.version)))

    return join_header_words([h])


class MyCookieJar(LWPCookieJar):

    def as_lwp_str(self, ignore_discard=True, ignore_expires=True):
        """Return cookies as a string of "\\n"-separated "Set-Cookie3" headers.

        ignore_discard and ignore_expires: see docstring for FileCookieJar.save

        """
        now = time.time()
        r = []
        for cookie in self:
            if not ignore_discard and cookie.discard:
                continue
            if not ignore_expires and cookie.is_expired(now):
                continue
            r.append("Set-Cookie3: %s" % lwp_cookie_str(cookie))

        return "\n".join(r+[""])

    def save(self, filename=None, ignore_discard=False, ignore_expires=False):
        if filename is None:
            if self.filename is not None: filename = self.filename
            else: raise ValueError(MISSING_FILENAME_TEXT)

        f = open(filename, "w")
        try:
            # There really isn't an LWP Cookies 2.0 format, but this indicates
            # that there is extra information in here (domain_dot and
            # port_spec) while still being compatible with libwww-perl, I hope.
            f.write("#LWP-Cookies-2.0\n")
            f.write(self.as_lwp_str(ignore_discard, ignore_expires))
        except:
            print "ERROR-SAVING-COOKIES"
        finally:
            f.close()

