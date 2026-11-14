"""Registry: which generator answers which gap.

    @generator("no_dockerfile")          # runs when the gap list contains this issue
    def dockerfile(scan, gaps): ...      # returns a list of Artifact

A generator that lists no issues is a helper: it runs on every call and decides by itself whether it has anything to add.
Adding a new kind of file means adding one decorated function; nothing else changes."""
GENERATORS = []


def generator(*issues):
    def wrap(fn):
        GENERATORS.append((tuple(issues), fn))
        return fn
    return wrap
