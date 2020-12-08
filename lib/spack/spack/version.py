# Copyright 2013-2020 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

"""
This module implements Version and version-ish objects.  These are:

Version
  A single version of a package.
VersionRange
  A range of versions of a package.
VersionList
  A list of Versions and VersionRanges.

All of these types support the following operations, which can
be called on any of the types::

  __eq__, __ne__, __lt__, __gt__, __ge__, __le__, __hash__
  __contains__
  satisfies
  overlaps
  union
  intersection
  concrete
"""
import re
import numbers
from bisect import bisect_left
from functools import wraps
from six import string_types

from llnl.util.lang import memoized

import spack.error
from spack.util.spack_yaml import syaml_dict


__all__ = ['Version', 'VersionRange', 'VersionList', 'ver']

# Valid version characters
VALID_VERSION = r'[A-Za-z0-9_\.\*\-]'

# Infinity-like versions. The order in the list implies the comparison rules
infinity_versions = ['develop', 'main', 'master', 'head', 'trunk']


def int_if_int(string):
    """Convert a string to int if possible.  Otherwise, return a string."""
    try:
        return int(string)
    except ValueError:
        return string


def coerce_versions(a, b):
    """
    Convert both a and b to the 'greatest' type between them, in this order:
           Version < VersionRange < VersionList
    This is used to simplify comparison operations below so that we're always
    comparing things that are of the same type.
    """
    order = (Version, VersionRange, VersionList)
    ta, tb = type(a), type(b)

    def check_type(t):
        if t not in order:
            raise TypeError("coerce_versions cannot be called on %s" % t)
    check_type(ta)
    check_type(tb)

    if ta == tb:
        return (a, b)
    elif order.index(ta) > order.index(tb):
        if ta == VersionRange:
            return (a, VersionRange(b, b))
        else:
            return (a, VersionList([b]))
    else:
        if tb == VersionRange:
            return (VersionRange(a, a), b)
        else:
            return (VersionList([a]), b)


def coerced(method):
    """Decorator that ensures that argument types of a method are coerced."""
    @wraps(method)
    def coercing_method(a, b, *args, **kwargs):
        if type(a) == type(b) or a is None or b is None:
            return method(a, b, *args, **kwargs)
        else:
            ca, cb = coerce_versions(a, b)
            return getattr(ca, method.__name__)(cb, *args, **kwargs)
    return coercing_method


class Version(object):
    """Class to represent versions"""

    def __init__(self, string):
        string = str(string)

        if not re.match(VALID_VERSION, string):
            raise ValueError("Bad characters in version string: %s" % string)

        # preserve the original string, but trimmed.
        string = string.strip()
        self.string = string

        # Split version into alphabetical and numeric segments
        segment_regex = r'[a-zA-Z]+|[0-9]+'
        segments = re.findall(segment_regex, string)
        self.version = tuple(int_if_int(seg) for seg in segments)

        # Store the separators from the original version string as well.
        self.separators = tuple(re.split(segment_regex, string)[1:])

    @property
    def dotted(self):
        """The dotted representation of the version.

        Example:
        >>> version = Version('1-2-3b')
        >>> version.dotted
        Version('1.2.3b')

        Returns:
            Version: The version with separator characters replaced by dots
        """
        return Version(self.string.replace('-', '.').replace('_', '.'))

    @property
    def underscored(self):
        """The underscored representation of the version.

        Example:
        >>> version = Version('1.2.3b')
        >>> version.underscored
        Version('1_2_3b')

        Returns:
            Version: The version with separator characters replaced by
                underscores
        """
        return Version(self.string.replace('.', '_').replace('-', '_'))

    @property
    def dashed(self):
        """The dashed representation of the version.

        Example:
        >>> version = Version('1.2.3b')
        >>> version.dashed
        Version('1-2-3b')

        Returns:
            Version: The version with separator characters replaced by dashes
        """
        return Version(self.string.replace('.', '-').replace('_', '-'))

    @property
    def joined(self):
        """The joined representation of the version.

        Example:
        >>> version = Version('1.2.3b')
        >>> version.joined
        Version('123b')

        Returns:
            Version: The version with separator characters removed
        """
        return Version(
            self.string.replace('.', '').replace('-', '').replace('_', ''))

    def up_to(self, index):
        """The version up to the specified component.

        Examples:
        >>> version = Version('1.23-4b')
        >>> version.up_to(1)
        Version('1')
        >>> version.up_to(2)
        Version('1.23')
        >>> version.up_to(3)
        Version('1.23-4')
        >>> version.up_to(4)
        Version('1.23-4b')
        >>> version.up_to(-1)
        Version('1.23-4')
        >>> version.up_to(-2)
        Version('1.23')
        >>> version.up_to(-3)
        Version('1')

        Returns:
            Version: The first index components of the version
        """
        return self[:index]

    def lowest(self):
        return self

    def highest(self):
        return self

    def isdevelop(self):
        """Triggers on the special case of the `@develop-like` version."""
        for inf in infinity_versions:
            for v in self.version:
                if v == inf:
                    return True

        return False

    @coerced
    def satisfies(self, other):
        """A Version 'satisfies' another if it is at least as specific and has
        a common prefix.  e.g., we want gcc@4.7.3 to satisfy a request for
        gcc@4.7 so that when a user asks to build with gcc@4.7, we can find
        a suitable compiler.
        """

        nself = len(self.version)
        nother = len(other.version)
        return nother <= nself and self.version[:nother] == other.version

    def __iter__(self):
        return iter(self.version)

    def __len__(self):
        return len(self.version)

    def __getitem__(self, idx):
        cls = type(self)

        if isinstance(idx, numbers.Integral):
            return self.version[idx]

        elif isinstance(idx, slice):
            string_arg = []

            pairs = zip(self.version[idx], self.separators[idx])
            for token, sep in pairs:
                string_arg.append(str(token))
                string_arg.append(str(sep))

            string_arg.pop()  # We don't need the last separator
            string_arg = ''.join(string_arg)
            return cls(string_arg)

        message = '{cls.__name__} indices must be integers'
        raise TypeError(message.format(cls=cls))

    def __repr__(self):
        return 'Version(' + repr(self.string) + ')'

    def __str__(self):
        return self.string

    def __format__(self, format_spec):
        return self.string.format(format_spec)

    @property
    def concrete(self):
        return self

    # TODO: consider @memoized since we impl __hash__?
    @coerced
    def __lt__(self, other):
        """Version comparison is designed for consistency with the way RPM
           does things.  If you need more complicated versions in installed
           packages, you should override your package's version string to
           express it more sensibly.
        """
        if other is None:
            return False

        # Coerce if other is not a Version
        # simple equality test first.
        if self.version == other.version:
            return False

        # Standard comparison of two numeric versions
        for a, b in zip(self.version, other.version):
            if a == b:
                continue
            else:
                if a in infinity_versions:
                    if b in infinity_versions:
                        return (infinity_versions.index(a) >
                                infinity_versions.index(b))
                    else:
                        return False
                if b in infinity_versions:
                    return True

                # Neither a nor b is infinity
                # Numbers are always "newer" than letters.
                # This is for consistency with RPM.  See patch
                # #60884 (and details) from bugzilla #50977 in
                # the RPM project at rpm.org.  Or look at
                # rpmvercmp.c if you want to see how this is
                # implemented there.
                if type(a) != type(b):
                    return type(b) == int
                else:
                    return a < b

        # If the common prefix is equal, the one
        # with more segments is bigger.
        return len(self.version) < len(other.version)

    @coerced
    def __eq__(self, other):
        return (other is not None and
                type(other) == Version and self.version == other.version)

    @coerced
    def __ne__(self, other):
        return not (self == other)

    @coerced
    def __le__(self, other):
        return self == other or self < other

    @coerced
    def __ge__(self, other):
        return not (self < other)

    @coerced
    def __gt__(self, other):
        return not (self == other) and not (self < other)

    def __hash__(self):
        return hash(self.version)

    @coerced
    def __contains__(self, other):
        if other is None:
            return False
        return other.version[:len(self.version)] == self.version

    def is_predecessor(self, other):
        """True if the other version is the immediate predecessor of this one.
           That is, NO versions v exist such that:
           (self < v < other and v not in self).
        """
        if len(self.version) != len(other.version):
            return False

        sl = self.version[-1]
        ol = other.version[-1]
        return type(sl) == int and type(ol) == int and (ol - sl == 1)

    def is_successor(self, other):
        return other.is_predecessor(self)

    @coerced
    def overlaps(self, other):
        return self in other or other in self

    @coerced
    def union(self, other):
        if self == other or other in self:
            return self
        elif self in other:
            return other
        else:
            return VersionList([self, other])

    @coerced
    def intersection(self, other):
        if self == other:
            return self
        else:
            return VersionList()


def _endpoint_only(fun):
    """We want to avoid logic that handles any type of version range, just endpoints."""
    @wraps(fun)
    def validate_endpoint_argument(self, other):
        assert isinstance(other, _VersionEndpoint), "required two _VersionEndpoint arguments, received {0} and {1}".format(self, other)
        assert self.location == other.location, "two _VersionEndpoint arguments with different locations is a programming bug: received {0} and {1}".format(self, other)
        return fun(self, other)
    return validate_endpoint_argument


class _VersionEndpoint(object):

    _valid_endpoint_locations = frozenset(['left', 'right'])

    def __init__(self, value, location, includes_endpoint):
        assert (value is None) or isinstance(value, Version), value
        assert location in self._valid_endpoint_locations, location
        assert isinstance(includes_endpoint, bool)

        # We arbitrarily decide this is a nonsensical state, consistent with
        # VersionRange.__init__().
        if value is None:
            assert includes_endpoint, "infinite (None) value is incompatible with includes_endpoint=False"

        self.value = value
        self.location = location
        self.includes_endpoint = includes_endpoint

    def __repr__(self):
        return "_VersionEndpoint(value={0!r}, location={1!r}, includes_endpoint={2!r})".format(
            self.value, self.location, self.includes_endpoint
        )

    def __hash__(self):
        return hash((self.value, self.location, self.includes_endpoint))

    @_endpoint_only
    def __eq__(self, other):
        return (self.value == other.value and
                # Note that this is already checked by @_endpoint_only.
                self.location == other.location and
                self.includes_endpoint == other.includes_endpoint)

    # TODO: consider @memoized since we impl __hash__?
    @_endpoint_only
    def __lt__(self, other):
        s, o = self, other

        # (1) Check whether both are the same finite value, or both are the same
        #     infinite value (None).
        if s.value == o.value:
            # Same version, so we check whether one and not the other contains
            # the endpoint.
            if s.includes_endpoint != o.includes_endpoint:
                return s.includes_endpoint
            # Cannot prove strict '<', so False.
            return False

        # (2) We now know they aren't *both* infinite, since they're not
        #     equal, so we have to see if *one* is, and assume it is less/greater
        #     than the other regardless of the other's value.
        # TODO: This is already checked by @_endpoint_only.
        assert self.location == other.location
        if self.location == 'left':
            infinite_left_wins = True
        else:
            # TODO: This is already checked by __init__.
            assert self.location == 'right'
            infinite_left_wins = False
        if s.value is None:
            return infinite_left_wins
        if o.value is None:
            return not infinite_left_wins

        return s.value < o.value

    @_endpoint_only
    def __ne__(self, other):
        return not (self == other)

    @_endpoint_only
    def __le__(self, other):
        return self == other or self < other

    @_endpoint_only
    def __ge__(self, other):
        return not (self < other)

    @_endpoint_only
    def __gt__(self, other):
        return not (self == other) and not (self < other)


class VersionRange(object):

    @classmethod
    def has_star_component(cls, obj):
        if not obj:
            return False
        if isinstance(obj, str):
            obj = Version(obj)
        assert isinstance(obj, Version), obj
        for sep in obj.dotted.separators:
            if sep.startswith('.*'):
                return True
        return False

    @classmethod
    def check_for_star_components(
        cls, start, end, includes_left_endpoint, includes_right_endpoint,
        description=None,
    ):
        if isinstance(start, string_types):
            start = Version(start)
        if isinstance(end, string_types):
            end = Version(end)

        would_be_range = VersionRange(start, end,
                                      includes_left_endpoint,
                                      includes_right_endpoint)
        any_dotted_versions = []
        for edge in [start, end]:
            if cls.has_star_component(edge):
                any_dotted_versions.append(edge)

        if start != end:
            if any_dotted_versions:
                if description is None:
                    description = str(would_be_range)
                raise ValueError(
                    "cannot create version range inequality '{0}' "
                    "with starred versions: [{1}].\n"
                    "please remove all '.*' version components "
                    "or suffixes from your input specs"
                    .format(description,
                            ', '.join(
                                v.string
                                for v in any_dotted_versions
                            )))
            return would_be_range

        assert start == end
        assert includes_left_endpoint == includes_right_endpoint

        if len(any_dotted_versions) == 0:
            return would_be_range
        assert start is not None

        version_components = list(start.version)
        suffix = ''
        if not isinstance(version_components[-1], int):
            suffix = version_components.pop()
        low_end = version_components[:]
        high_end = low_end[:]
        high_end[-1] += 1

        # NB: Using the same start.separators will still give us a version with
        # the same .\*, so remove it before zipping.
        fixed_seps = [re.sub(r'^.\*', '', s) for s in start.separators]

        low_ver = Version(''.join(
            str(k) + str(v) for k, v in zip(low_end, fixed_seps)
        ) + suffix)
        high_ver = Version(''.join(
            str(k) + str(v) for k, v in zip(high_end, fixed_seps)
        ) + suffix)

        if not includes_left_endpoint:
            assert not includes_right_endpoint
            low_side = cls(None, low_ver,
                           includes_left_endpoint=True,
                           includes_right_endpoint=False)
            high_side = cls(high_ver, None,
                            includes_left_endpoint=True,
                            includes_right_endpoint=True)
            return VersionList([low_side, high_side])

        return cls(low_ver, high_ver,
                   includes_left_endpoint=True,
                   includes_right_endpoint=False)

    def __init__(self, start, end, includes_left_endpoint=True,
                 includes_right_endpoint=True):
        if isinstance(start, string_types):
            start = Version(start)
        if isinstance(end, string_types):
            end = Version(end)

        self.start = start
        self.end = end

        if start and end and end < start:
            raise ValueError("Invalid Version range: %s" % self)

        assert isinstance(includes_left_endpoint, bool)
        assert isinstance(includes_right_endpoint, bool)

        self.includes_left_endpoint = includes_left_endpoint
        self.includes_right_endpoint = includes_right_endpoint

        # We don't enforce this anywhere except implicitly when parsing
        # a version string, but it is an assumption we have made so far, so we
        # might as well check it.
        if start is None:
            assert includes_left_endpoint
        if end is None:
            assert includes_right_endpoint

    def lowest(self):
        return self.start

    def _low_endpoint(self):
        return _VersionEndpoint(self.lowest(), 'left', self.includes_left_endpoint)

    def highest(self):
        return self.end

    def _high_endpoint(self):
        return _VersionEndpoint(self.highest(), 'right', self.includes_right_endpoint)

    @coerced
    def __lt__(self, other):
        """Sort VersionRanges lexicographically so that they are ordered first
           by start and then by end.  None denotes an open range, so None in
           the start position is less than everything except None, and None in
           the end position is greater than everything but None.
        """
        if other is None:
            return False

        s, o = self, other

        # Check left endpoint.
        if s._low_endpoint() < o._low_endpoint():
            return True

        # Check right endpoint.
        return s._high_endpoint() < o._high_endpoint()

    @coerced
    def __eq__(self, other):
        return (other is not None and
                type(other) == VersionRange and
                self.start == other.start and self.end == other.end and
                self.includes_left_endpoint == other.includes_left_endpoint and
                self.includes_right_endpoint == other.includes_right_endpoint)

    @coerced
    def __ne__(self, other):
        return not (self == other)

    @coerced
    def __le__(self, other):
        return self == other or self < other

    @coerced
    def __ge__(self, other):
        return not (self < other)

    @coerced
    def __gt__(self, other):
        return not (self == other) and not (self < other)

    @property
    def concrete(self):
        if self.start != self.end:
            return None
        # :
        if self.start is None:
            assert self.end is None
            return None
        # {0}
        if self.includes_left_endpoint or self.includes_right_endpoint:
            # Recall that :!1.2.3: => :.
            assert self.includes_left_endpoint == self.includes_right_endpoint
            return self.start
        # :!{0}!:
        return None

    @coerced
    def __contains__(self, other):
        if other is None:
            return False

        in_lower = (
            ((self.start == other.start) and
             not self.includes_left_endpoint or
             other.includes_left_endpoint) or
            self.start is None or
            (other.start is not None and (
                self.start < other.start or
                other.start in self.start)))
        if not in_lower:
            return False

        in_upper = (
            ((self.end == other.end) and
             not self.includes_right_endpoint
             or other.includes_right_endpoint) or
            self.end is None or
            (other.end is not None and (
                self.end > other.end or
                other.end in self.end)))
        return in_upper

    @coerced
    def satisfies(self, other):
        """A VersionRange satisfies another if some version in this range
        would satisfy some version in the other range.  To do this it must
        either:

        a) Overlap with the other range
        b) The start of this range satisfies the end of the other range.

        This is essentially the same as overlaps(), but overlaps assumes
        that its arguments are specific.  That is, 4.7 is interpreted as
        4.7.0.0.0.0... .  This function assumes that 4.7 would be satisfied
        by 4.7.3.5, etc.

        Rationale:

        If a user asks for gcc@4.5:4.7, and a package is only compatible with
        gcc@4.7.3:4.8, then that package should be able to build under the
        constraints.  Just using overlaps() would not work here.

        Note that we don't need to check whether the end of this range
        would satisfy the start of the other range, because overlaps()
        already covers that case.

        Note further that overlaps() is a symmetric operation, while
        satisfies() is not.
        """
        return (self.overlaps(other) or
                # if either self.start or other.end are None, then this can't
                # satisfy, or overlaps() would've taken care of it.
                self.start and other.end and self.start.satisfies(other.end))

    @coerced
    def overlaps(self, other):
        return ((self.start is None or other.end is None or
                 self.start <= other.end or
                 other.end in self.start or self.start in other.end) and
                (other.start is None or self.end is None or
                 other.start <= self.end or
                 other.start in self.end or self.end in other.start))

    @coerced
    def union(self, other):
        if not self.overlaps(other):
            if (self.end is not None and other.start is not None and
                    self.end.is_predecessor(other.start)):
                return VersionRange(self.start, other.end)

            if (other.end is not None and self.start is not None and
                    other.end.is_predecessor(self.start)):
                return VersionRange(other.start, self.end)

            return VersionList([self, other])

        # if we're here, then we know the ranges overlap.
        if self.start is None or other.start is None:
            start = None
        else:
            start = self.start
            # TODO: See note in intersection() about < and in discrepancy.
            if self.start in other.start or other.start < self.start:
                start = other.start

        if self.end is None or other.end is None:
            end = None
        else:
            end = self.end
            # TODO: See note in intersection() about < and in discrepancy.
            if other.end not in self.end:
                if end in other.end or other.end > self.end:
                    end = other.end

        return VersionRange(start, end)

    @coerced
    def intersection(self, other):
        if self.overlaps(other):
            if self.start is None:
                start = other.start
            else:
                start = self.start
                if other.start is not None:
                    if other.start > start or other.start in start:
                        start = other.start

            if self.end is None:
                end = other.end
            else:
                end = self.end
                # TODO: does this make sense?
                # This is tricky:
                #     1.6.5 in 1.6 = True  (1.6.5 is more specific)
                #     1.6 < 1.6.5  = True  (lexicographic)
                # Should 1.6 NOT be less than 1.6.5?  Hmm.
                # Here we test (not end in other.end) first to avoid paradox.
                # FIXME: this seems to make perfect sense? Has this code ever
                # stopped any error?
                if other.end is not None and end not in other.end:
                    if other.end < end or other.end in end:
                        end = other.end

            return VersionRange(start, end)

        else:
            return VersionList()

    def __hash__(self):
        return hash((self.start, self.end))

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        # ( :!1.2.3!: | 1.2.3 | : )
        if self.start == self.end:
            # :
            if self.start is None:
                assert self.end is None
                return ':'
            assert self.includes_left_endpoint == self.includes_right_endpoint
            # 1.2.3
            if self.includes_left_endpoint:
                assert self.includes_right_endpoint
                return str(self.start)
            # :!1.2.3!:
            return ":!{0}!:".format(self.start)

        # ( :!1.2.3 | :1.2.3 )
        if self.start is None:
            # Checked that self.start == self.end above.
            assert self.end is not None
            assert self.includes_left_endpoint
            # :1.2.3
            if self.includes_right_endpoint:
                return ':{0}'.format(self.end)
            # :!1.2.3
            return ':!{0}'.format(self.end)

        # ( 1.2.3: | 1.2.3!: )
        if self.end is None:
            assert self.start is not None
            assert self.includes_right_endpoint
            # 1.2.3:
            if self.includes_left_endpoint:
                return '{0}:'.format(self.start)
            # 1.2.3!:
            return '{0}!:'.format(self.start)

        assert (self.start is not None and
                self.end is not None and
                self.start != self.end)

        # {0}!:!{1} => {0} < x < {1}
        if (not self.includes_left_endpoint and
            not self.includes_right_endpoint):
            return '{0}!:!{1}'.format(self.start, self.end)
        # {0}:!{1} => {0} <= x < {1}
        if not self.includes_right_endpoint:
            return '{0}:!{1}'.format(self.start, self.end)
        # {0}!:{1} => {0} < x <= {1}
        if not self.includes_left_endpoint:
            return '{0}!:{1}'.format(self.start, self.end)
        # {0}:{1} => {0} <= x <= {1}
        assert self.includes_left_endpoint and self.includes_right_endpoint
        return "{0}:{1}".format(self.start, self.end)


class VersionList(object):
    """Sorted, non-redundant list of Versions and VersionRanges."""

    def __init__(self, vlist=None):
        self.versions = []
        if vlist is not None:
            if isinstance(vlist, string_types):
                vlist = _string_to_version(vlist)
                if type(vlist) == VersionList:
                    self.versions = vlist.versions
                else:
                    self.versions = [vlist]
            else:
                vlist = list(vlist)
                for v in vlist:
                    self.add(ver(v))

    def add(self, version):
        if type(version) in (Version, VersionRange):
            # This normalizes single-value version ranges.
            if version.concrete:
                version = version.concrete

            i = bisect_left(self, version)

            while i - 1 >= 0 and version.overlaps(self[i - 1]):
                version = version.union(self[i - 1])
                del self.versions[i - 1]
                i -= 1

            while i < len(self) and version.overlaps(self[i]):
                version = version.union(self[i])
                del self.versions[i]

            self.versions.insert(i, version)

        elif type(version) == VersionList:
            for v in version:
                self.add(v)

        else:
            raise TypeError("Can't add %s to VersionList" % type(version))

    @property
    def concrete(self):
        if len(self) == 1:
            return self[0].concrete
        else:
            return None

    def copy(self):
        return VersionList(self)

    def lowest(self):
        """Get the lowest version in the list."""
        if not self:
            return None
        else:
            return self[0].lowest()

    def highest(self):
        """Get the highest version in the list."""
        if not self:
            return None
        else:
            return self[-1].highest()

    def highest_numeric(self):
        """Get the highest numeric version in the list."""
        numeric_versions = list(filter(
            lambda v: str(v) not in infinity_versions,
            self.versions))
        if not any(numeric_versions):
            return None
        else:
            return numeric_versions[-1].highest()

    def preferred(self):
        """Get the preferred (latest) version in the list."""
        latest = self.highest_numeric()
        if latest is None:
            latest = self.highest()
        return latest

    @coerced
    def overlaps(self, other):
        if not other or not self:
            return False

        s = o = 0
        while s < len(self) and o < len(other):
            if self[s].overlaps(other[o]):
                return True
            elif self[s] < other[o]:
                s += 1
            else:
                o += 1
        return False

    def to_dict(self):
        """Generate human-readable dict for YAML."""
        if self.concrete:
            return syaml_dict([
                ('version', str(self[0]))
            ])
        else:
            return syaml_dict([
                ('versions', [str(v) for v in self])
            ])

    @staticmethod
    def from_dict(dictionary):
        """Parse dict from to_dict."""
        if 'versions' in dictionary:
            return VersionList(dictionary['versions'])
        elif 'version' in dictionary:
            return VersionList([dictionary['version']])
        else:
            raise ValueError("Dict must have 'version' or 'versions' in it.")

    @coerced
    def satisfies(self, other, strict=False):
        """A VersionList satisfies another if some version in the list
           would satisfy some version in the other list.  This uses
           essentially the same algorithm as overlaps() does for
           VersionList, but it calls satisfies() on member Versions
           and VersionRanges.

           If strict is specified, this version list must lie entirely
           *within* the other in order to satisfy it.
        """
        if not other or not self:
            return False

        if strict:
            return self in other

        s = o = 0
        while s < len(self) and o < len(other):
            if self[s].satisfies(other[o]):
                return True
            elif self[s] < other[o]:
                s += 1
            else:
                o += 1
        return False

    @coerced
    def update(self, other):
        for v in other.versions:
            self.add(v)

    @coerced
    def union(self, other):
        result = self.copy()
        result.update(other)
        return result

    @coerced
    def intersection(self, other):
        # TODO: make this faster.  This is O(n^2).
        result = VersionList()
        for s in self:
            for o in other:
                result.add(s.intersection(o))
        return result

    @coerced
    def intersect(self, other):
        """Intersect this spec's list with other.

        Return True if the spec changed as a result; False otherwise
        """
        isection = self.intersection(other)
        changed = (isection.versions != self.versions)
        self.versions = isection.versions
        return changed

    @coerced
    def __contains__(self, other):
        if len(self) == 0:
            return False

        for version in other:
            i = bisect_left(self, other)
            if i == 0:
                if version not in self[0]:
                    return False
            elif all(version not in v for v in self[i - 1:]):
                return False

        return True

    def __getitem__(self, index):
        return self.versions[index]

    def __iter__(self):
        return iter(self.versions)

    def __reversed__(self):
        return reversed(self.versions)

    def __len__(self):
        return len(self.versions)

    def __bool__(self):
        return bool(self.versions)

    @coerced
    def __eq__(self, other):
        return other is not None and self.versions == other.versions

    @coerced
    def __ne__(self, other):
        return not (self == other)

    @coerced
    def __lt__(self, other):
        return other is not None and self.versions < other.versions

    @coerced
    def __le__(self, other):
        return self == other or self < other

    @coerced
    def __ge__(self, other):
        return not (self < other)

    @coerced
    def __gt__(self, other):
        return not (self == other) and not (self < other)

    def __hash__(self):
        return hash(tuple(self.versions))

    def __str__(self):
        return ",".join(str(v) for v in self.versions)

    def __repr__(self):
        return str(self.versions)


def _string_to_version(string):
    """Converts a string to a Version, VersionList, or VersionRange.
       This is private.  Client code should use ver().
    """
    string = string.replace(' ', '')

    if ',' in string:
        return VersionList(string.split(','))

    elif ':' in string:
        s, e = string.split(':')
        start = Version(s) if s else None
        end = Version(e) if e else None
        return VersionRange(start, end)

    else:
        return Version(string)


def ver(obj):
    """Parses a Version, VersionRange, or VersionList from a string
       or list of strings.
    """
    if isinstance(obj, (list, tuple)):
        return VersionList(obj)
    elif isinstance(obj, string_types):
        return ver(_string_to_version(obj))
    elif isinstance(obj, (int, float)):
        return _string_to_version(str(obj))
    elif type(obj) in (Version, VersionRange, VersionList):
        if isinstance(obj, Version) and VersionRange.has_star_component(obj):
            return VersionRange.check_for_star_components(obj, obj, True, True)
        return obj
    else:
        raise TypeError("ver() can't convert %s to version!" % type(obj))


class VersionError(spack.error.SpackError):
    """This is raised when something is wrong with a version."""


class VersionChecksumError(VersionError):
    """Raised for version checksum errors."""
