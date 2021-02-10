# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack import *


class Ipopt(AutotoolsPackage):
    """Ipopt (Interior Point OPTimizer, pronounced eye-pea-Opt) is a
       software package for large-scale nonlinear optimization."""
    homepage = "https://projects.coin-or.org/Ipopt"
    url      = "http://www.coin-or.org/download/source/Ipopt/Ipopt-3.12.4.tgz"
    git      = "https://github.com/coin-or/Ipopt.git"

    version('3.13.3',  tag='releases/3.13.3')
    version('3.13.2',  tag='releases/3.13.2')
    version('3.13.1',  tag='releases/3.13.1')
    version('3.13.0',  tag='releases/3.13.0')
    version('3.12.13', tag='releases/3.12.13')
    version('3.12.12', tag='releases/3.12.12')
    version('3.12.11', tag='releases/3.12.11')
    version('3.12.10', tag='releases/3.12.10')
    version('3.12.9',  tag='releases/3.12.9')
    version('3.12.8',  tag='releases/3.12.8')
    version('3.12.7',  tag='releases/3.12.7')
    version('3.12.6',  tag='releases/3.12.6')
    version('3.12.5',  tag='releases/3.12.5')
    version('3.12.4',  tag='releases/3.12.4')
    version('3.12.3',  tag='releases/3.12.3')
    version('3.12.2',  tag='releases/3.12.2')
    version('3.12.1',  tag='releases/3.12.1')
    version('3.12.0',  tag='releases/3.12.0')

    variant('coinhsl', default=False,
            description="Build with Coin Harwell Subroutine Libraries")
    variant('metis', default=False,
            description="Build with METIS partitioning support")
    variant('debug', default=False,
            description="Build debug instead of optimized version")
    variant('mumps', default=True,
            description='Build with support for linear solver MUMPS')

    depends_on("blas")
    depends_on("lapack")
    depends_on("pkgconfig", type='build')
    depends_on("mumps+double~mpi", when='+mumps')
    depends_on('coinhsl', when='+coinhsl')
    depends_on('metis@4.0:', when='+metis')

    # Must have at least one linear solver available!
    conflicts('~mumps', when='~coinhsl')

    patch('ipopt_ppc_build.patch', when='arch=ppc64le')

    flag_handler = build_system_flags
    build_directory = 'spack-build'

    # IPOPT does not build correctly in parallel on OS X
    parallel = False

    def configure_args(self):
        spec = self.spec
        # Dependency directories
        blas_dir = spec['blas'].prefix
        lapack_dir = spec['lapack'].prefix

        blas_lib = spec['blas'].libs.ld_flags
        lapack_lib = spec['lapack'].libs.ld_flags

        args = [
            "--prefix=%s" % self.prefix,
            "--enable-shared",
            "coin_skip_warn_cxxflags=yes",
            "--with-blas-incdir=%s" % blas_dir.include,
            "--with-blas-lib=%s" % blas_lib,
            "--with-lapack-incdir=%s" % lapack_dir.include,
            "--with-lapack-lib=%s" % lapack_lib
        ]

        if '+mumps' in spec:
            # Add directory with fake MPI headers in sequential MUMPS
            # install to header search path
            mumps_dir = spec['mumps'].prefix
            mumps_flags = "-ldmumps -lmumps_common -lpord -lmpiseq"
            mumps_libcmd = "-L%s " % mumps_dir.lib + mumps_flags
            args.extend([
                "--with-mumps-incdir=%s" % mumps_dir.include,
                "--with-mumps-lib=%s" % mumps_libcmd])

        if 'coinhsl' in spec:
            args.extend([
                '--with-hsl-lib=%s' % spec['coinhsl'].libs.ld_flags,
                '--with-hsl-incdir=%s' % spec['coinhsl'].prefix.include])

        if 'metis' in spec:
            args.extend([
                '--with-metis-lib=%s' % spec['metis'].libs.ld_flags,
                '--with-metis-incdir=%s' % spec['metis'].prefix.include])

        # The IPOPT configure file states that '--enable-debug' implies
        # '--disable-shared', but adding '--enable-shared' overrides
        # '--disable-shared' and builds a shared library with debug symbols
        if '+debug' in spec:
            args.append('--enable-debug')
        else:
            args.append('--disable-debug')

        return args
