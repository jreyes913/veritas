#!/bin/bash

# ---------------------------------------------------------------------------
# veritasc — compile a .ver source file to a native binary
#
# Usage:  ./veritasc.sh <file.ver>
#
# Automatically detects included libraries from the .ver source and maps
# them to the correct gcc linker flags.
# ---------------------------------------------------------------------------

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <source.ver> [--tokens|--ast|--ir|--semantics]" >&2
    exit 1
fi

source_file="$1"
shift

debug_flags=()
for arg in "$@"; do
    case "$arg" in
        --tokens|--ast|--ir|--semantics)
            debug_flags+=("$arg")
            ;;
        *)
            echo "Unknown flag: $arg" >&2
            exit 1
            ;;
    esac
done

filename=$(echo "$source_file" | sed 's/\.ver$//g')

# --- 1. Transpile .ver → .c ------------------------------------------------
if [[ ${#debug_flags[@]} -gt 0 ]]; then
    python3 vcparser.py "${filename}.ver" "${debug_flags[@]}"
    exit 0
fi

python3 vcparser.py "${filename}.ver" > "${filename}.c"

# --- 2. Library → linker flag map ------------------------------------------
#
# Format:  ["header"]="flag1 flag2 ..."   (space-separated when multi-flag)
#
# Sections:
#   A.  C standard library (mostly no flags needed; listed for completeness)
#   B.  POSIX / system
#   C.  Math & numerics
#   D.  Linear algebra (C-native)
#   E.  Statistics & probability (C-native)
#   F.  Signal processing & FFT
#   G.  Optimisation & solvers
#   H.  Sparse matrices
#   I.  Random number generation
#   J.  Data formats & I/O
#   K.  Networking & IPC
#   L.  Compression
#   M.  Cryptography & hashing
#   N.  String handling & Unicode
#   O.  Date & time
#   P.  Terminal & UI
#   Q.  Graphics & image
#   R.  Audio
#   S.  Database
#   T.  Parallelism & concurrency
#   U.  Debugging & profiling
#   V.  Portability / utility

declare -A LIB_MAP=(

    # -----------------------------------------------------------------------
    # A. C STANDARD LIBRARY
    #    Headers are part of libc; no extra -l flag required.
    # -----------------------------------------------------------------------
    ["stdio.h"]=""
    ["stdlib.h"]=""
    ["stdint.h"]=""
    ["stddef.h"]=""
    ["stdbool.h"]=""
    ["stdarg.h"]=""
    ["stdnoreturn.h"]=""
    ["string.h"]=""
    ["strings.h"]=""
    ["ctype.h"]=""
    ["wctype.h"]=""
    ["wchar.h"]=""
    ["locale.h"]=""
    ["limits.h"]=""
    ["float.h"]=""
    ["assert.h"]=""
    ["errno.h"]=""
    ["signal.h"]=""
    ["setjmp.h"]=""
    ["time.h"]=""
    ["inttypes.h"]=""
    ["complex.h"]=""
    ["tgmath.h"]=""
    ["fenv.h"]=""
    ["iso646.h"]=""
    ["stdalign.h"]=""
    ["stdatomic.h"]=""
    ["uchar.h"]=""

    # -----------------------------------------------------------------------
    # B. POSIX / SYSTEM
    # -----------------------------------------------------------------------
    ["unistd.h"]=""           # POSIX API — part of libc
    ["fcntl.h"]=""
    ["sys/types.h"]=""
    ["sys/stat.h"]=""
    ["sys/wait.h"]=""
    ["sys/mman.h"]=""         # mmap
    ["sys/ioctl.h"]=""
    ["sys/socket.h"]=""
    ["sys/select.h"]=""
    ["sys/epoll.h"]=""
    ["sys/eventfd.h"]=""
    ["sys/signalfd.h"]=""
    ["sys/timerfd.h"]=""
    ["sys/resource.h"]=""
    ["sys/utsname.h"]=""
    ["sys/sysinfo.h"]=""
    ["sys/ipc.h"]=""
    ["sys/shm.h"]=""
    ["sys/sem.h"]=""
    ["sys/msg.h"]=""
    ["sched.h"]=""
    ["poll.h"]=""
    ["dirent.h"]=""
    ["glob.h"]=""
    ["fnmatch.h"]=""
    ["wordexp.h"]=""
    ["getopt.h"]=""
    ["pthread.h"]="-lpthread"
    ["semaphore.h"]="-lpthread"
    ["dl.h"]="-ldl"
    ["dlfcn.h"]="-ldl"
    ["aio.h"]="-lrt"          # POSIX async I/O
    ["mqueue.h"]="-lrt"       # POSIX message queues
    ["syslog.h"]=""

    # -----------------------------------------------------------------------
    # C. MATH & GENERAL NUMERICS
    # -----------------------------------------------------------------------
    ["math.h"]="-lm"
    ["complex.h"]="-lm"       # also listed in std; -lm needed for csin etc.
    ["quadmath.h"]="-lquadmath -lm"   # GCC 128-bit float (__float128)
    ["mpfr.h"]="-lmpfr -lgmp -lm"    # GNU MPFR — arbitrary-precision float
    ["mpc.h"]="-lmpc -lmpfr -lgmp -lm"  # GNU MPC — arbitrary-precision complex
    ["gmp.h"]="-lgmp"                 # GNU MP — arbitrary-precision integers/rationals
    ["flint/flint.h"]="-lflint -lgmp -lmpfr -lm"  # FLINT — number theory
    ["arb.h"]="-larb -lflint -lgmp -lmpfr -lm"    # Arb — ball arithmetic (rigorous)
    ["isl/isl_val.h"]="-lisl"         # Integer Set Library

    # -----------------------------------------------------------------------
    # D. LINEAR ALGEBRA (C-native)
    # -----------------------------------------------------------------------

    # BLAS (Basic Linear Algebra Subprograms) — Reference implementation
    ["cblas.h"]="-lcblas -lm"

    # OpenBLAS — optimised BLAS + LAPACK, pure C/Fortran, no C++ dep
    ["openblas/cblas.h"]="-lopenblas -lm"
    ["openblas/lapacke.h"]="-lopenblas -lm"

    # LAPACK via LAPACKE (C interface to Fortran LAPACK)
    ["lapacke.h"]="-llapacke -llapack -lblas -lm"
    ["lapack.h"]="-llapack -lblas -lm"

    # ATLAS (Automatically Tuned Linear Algebra Software)
    ["atlas/cblas.h"]="-lcblas -latlas -lm"
    ["atlas/clapack.h"]="-llapack -lcblas -latlas -lm"

    # GSL — GNU Scientific Library (C-native, comprehensive)
    ["gsl/gsl_blas.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_linalg.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_matrix.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_vector.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_eigen.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_permutation.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_combination.h"]="-lgsl -lgslcblas -lm"

    # SuiteSparse — sparse direct solvers (C-native)
    ["SuiteSparse_config.h"]="-lsuitesparseconfig -lm"
    ["cholmod.h"]="-lcholmod -lamd -lcolamd -lcamd -lccolamd -lsuitesparseconfig -llapack -lblas -lm"
    ["umfpack.h"]="-lumfpack -lamd -lsuitesparseconfig -lm"
    ["amd.h"]="-lamd -lsuitesparseconfig -lm"
    ["colamd.h"]="-lcolamd -lsuitesparseconfig -lm"
    ["camd.h"]="-lcamd -lsuitesparseconfig -lm"
    ["ccolamd.h"]="-lccolamd -lsuitesparseconfig -lm"
    ["klu.h"]="-lklu -lamd -lcolamd -lsuitesparseconfig -lm"
    ["ldl.h"]="-lldl -lsuitesparseconfig -lm"
    ["btf.h"]="-lbtf -lsuitesparseconfig -lm"
    ["rbio.h"]="-lrbio -lsuitesparseconfig -lm"
    ["spqr.h"]="-lspqr -lcholmod -lsuitesparseconfig -llapack -lblas -lm"
    ["GraphBLAS.h"]="-lgraphblas -lm"   # SuiteSparse:GraphBLAS

    # LAPACK auxiliary
    ["f2c.h"]=""              # Fortran-to-C types; header only

    # Elemental / libflame (dense LA, C interface)
    ["FLAME.h"]="-lflame -lm"

    # MAGMA — GPU-accelerated LA (C interface)
    ["magma.h"]="-lmagma -lmagma_sparse -lcublas -lcudart -lm"
    ["magma_lapack.h"]="-lmagma -lcublas -lcudart -lm"

    # clBLAS — OpenCL BLAS
    ["clBLAS.h"]="-lclBLAS -lOpenCL -lm"

    # Eigen C bindings via Eigen C API (thin C wrapper)
    ["eigen_c_api.h"]="-leigen_c_api -lm"

    # PLASMA — Parallel LA for multicore (C-native)
    ["plasma.h"]="-lplasma -lcoreblas -llapacke -lopenblas -lm"

    # SuperLU — sparse direct solver (C-native)
    ["slu_ddefs.h"]="-lsuperlu -lm"
    ["superlu/slu_ddefs.h"]="-lsuperlu -lm"

    # ARPACK (C interface via ARPACK-NG)
    ["arpack/arpack.h"]="-larpack -llapack -lblas -lm"

    # Spectra C bindings
    ["trilinos/Tpetra_CrsMatrix.hpp"]=""  # C++ — skip

    # PRIMME — eigensolver (C-native)
    ["primme.h"]="-lprimme -llapack -lblas -lm"

    # Faddeeva (special functions for complex error function)
    ["Faddeeva.h"]="-lm"

    # -----------------------------------------------------------------------
    # E. STATISTICS & PROBABILITY (C-native)
    # -----------------------------------------------------------------------

    # GSL statistics modules (same link line as GSL linalg)
    ["gsl/gsl_statistics.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_statistics_double.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_histogram.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_fit.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_multifit.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_multifit_nlinear.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_cdf.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_randist.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_rng.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_qrng.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_integration.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_odeiv2.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_interpolation.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_spline.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_roots.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_min.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_multimin.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_permute.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_sort.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_wavelet.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_fft_complex.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_dft_complex.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_chebyshev.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_poly.h"]="-lgsl -lgslcblas -lm"
    ["gsl/gsl_sf.h"]="-lgsl -lgslcblas -lm"       # special functions
    ["gsl/gsl_complex.h"]="-lgsl -lgslcblas -lm"

    # apophenia — statistical modelling in C
    ["apop.h"]="-lapophenia -lgsl -lgslcblas -lsqlite3 -lm"

    # Cephes — C math library (special functions, distributions)
    ["cephes.h"]="-lcephes -lm"

    # CDFLIB (C port of DCDFLIB — CDFs for many distributions)
    ["cdflib.h"]="-lcdflib -lm"

    # Statistics from PARI/GP (C library)
    ["pari/pari.h"]="-lpari -lm"

    # libdist — probability distributions
    ["dist.h"]="-ldist -lm"

    # Nmath (standalone R math library, C-callable)
    ["Rmath.h"]="-lRmath -lm"

    # -----------------------------------------------------------------------
    # F. SIGNAL PROCESSING & FFT
    # -----------------------------------------------------------------------
    ["fftw3.h"]="-lfftw3 -lm"
    ["fftw3f.h"]="-lfftw3f -lm"           # single-precision FFTW
    ["fftw3l.h"]="-lfftw3l -lm"           # long-double FFTW
    ["fftw3q.h"]="-lfftw3q -lquadmath -lm"  # quad-precision FFTW
    ["fftpack.h"]="-lm"                    # FFTPACK (often statically linked)
    ["kiss_fft.h"]="-lkissfft -lm"         # KISS FFT
    ["pocketfft.h"]="-lm"                  # PocketFFT (header-heavy, -lm only)
    ["liquid/liquid.h"]="-lliquid -lm"     # liquid-dsp — SDR / DSP toolkit

    # -----------------------------------------------------------------------
    # G. OPTIMISATION & SOLVERS
    # -----------------------------------------------------------------------
    ["nlopt.h"]="-lnlopt -lm"             # NLopt — nonlinear optimisation
    ["ipopt/IpStdCInterface.h"]="-lipopt -lm"  # IPOPT (C interface)
    ["ceres/c_api.h"]="-lceres -lm"       # Ceres Solver C API
    ["glpk.h"]="-lglpk -lm"              # GLPK — linear programming
    ["coinor/Cbc_C_Interface.h"]="-lCbc -lCgl -lOsi -lClp -lCoinUtils -lm"  # CBC MILP
    ["clp/Clp_C_Interface.h"]="-lClp -lCoinUtils -lm"    # CLP LP solver
    ["highs_c_api.h"]="-lhighs -lm"      # HiGHS LP/MIP solver
    ["osqp/osqp.h"]="-losqp -lm"         # OSQP — quadratic programming
    ["ecos.h"]="-lecos -lm"              # ECOS — conic solver
    ["scs.h"]="-lscs -lm"               # SCS — conic solver
    ["daqp.h"]="-ldaqp -lm"             # DAQP — active-set QP
    ["copt.h"]="-lcopt -lm"             # Cardinal Optimizer

    # -----------------------------------------------------------------------
    # H. SPARSE MATRICES (beyond SuiteSparse, listed above)
    # -----------------------------------------------------------------------
    ["cs.h"]="-lcxsparse -lm"           # CXSparse — compact sparse library
    ["taucs.h"]="-ltaucs -llapack -lblas -lm"  # TAUCS sparse Cholesky
    ["pardiso.h"]="-lpardiso -lm"       # PARDISO (MKL or standalone)
    ["superlu_dist.h"]="-lsuperlu_dist -llapack -lblas -lm"  # SuperLU distributed

    # -----------------------------------------------------------------------
    # I. RANDOM NUMBER GENERATION
    # -----------------------------------------------------------------------
    ["gsl/gsl_rng.h"]="-lgsl -lgslcblas -lm"       # already listed; kept for discoverability
    ["pcg_basic.h"]="-lm"                           # PCG — header-only, -lm only
    ["mt19937ar.h"]="-lm"                           # Mersenne Twister
    ["randist.h"]="-lm"                             # librandist
    ["dieharder.h"]="-ldieharder -lgsl -lgslcblas -lm"  # Dieharder RNG tests
    ["trng/yarn2.hpp"]=""                            # C++ — skip
    ["Random123/philox.h"]="-lm"                    # Random123 (counter-based, header)

    # -----------------------------------------------------------------------
    # J. DATA FORMATS & I/O
    # -----------------------------------------------------------------------
    ["hdf5.h"]="-lhdf5 -lm"                        # HDF5 — hierarchical data
    ["hdf5_hl.h"]="-lhdf5_hl -lhdf5 -lm"           # HDF5 high-level API
    ["netcdf.h"]="-lnetcdf -lm"                     # NetCDF — array data
    ["csv.h"]="-lcsv"                               # libcsv — CSV parsing
    ["jansson.h"]="-ljansson"                        # JSON
    ["json-c/json.h"]="-ljson-c"                    # JSON-C
    ["cjson/cJSON.h"]="-lcjson"                     # cJSON
    ["yaml.h"]="-lyaml"                             # libyaml
    ["libxml/parser.h"]="-lxml2"                    # libxml2 — XML
    ["expat.h"]="-lexpat"                           # Expat XML parser
    ["toml.h"]="-ltoml-c"                           # toml-c
    ["msgpack.h"]="-lmsgpack"                        # MessagePack
    ["cbor.h"]="-lcbor"                             # libcbor
    ["arrow/c/abi.h"]="-larrow_c_bridge"            # Apache Arrow C ABI
    ["parquet.h"]="-lparquet -larrow -lm"           # Parquet (via Arrow)
    ["matio.h"]="-lmatio -lhdf5 -lm"               # MAT-file I/O (MATLAB format)

    # -----------------------------------------------------------------------
    # K. NETWORKING & IPC
    # -----------------------------------------------------------------------
    ["curl/curl.h"]="-lcurl"
    ["zmq.h"]="-lzmq"                              # ZeroMQ
    ["nanomsg/nn.h"]="-lnanomsg"                   # nanomsg
    ["nng/nng.h"]="-lnng"                          # NNG (next-gen nanomsg)
    ["rdkafka/rdkafka.h"]="-lrdkafka"              # librdkafka — Kafka client
    ["mosquitto.h"]="-lmosquitto"                  # MQTT (Eclipse Mosquitto)
    ["uv.h"]="-luv"                                # libuv — async I/O (Node.js engine)
    ["event.h"]="-levent"                          # libevent
    ["ev.h"]="-lev"                                # libev
    ["arpa/inet.h"]=""                             # POSIX — no flag
    ["netinet/in.h"]=""
    ["netdb.h"]=""
    ["ifaddrs.h"]=""
    ["resolv.h"]="-lresolv"
    ["ldap.h"]="-lldap -llber"
    ["grpc/grpc.h"]="-lgrpc"                       # gRPC C core

    # -----------------------------------------------------------------------
    # L. COMPRESSION
    # -----------------------------------------------------------------------
    ["zlib.h"]="-lz"
    ["bzlib.h"]="-lbz2"
    ["lzma.h"]="-llzma"                            # liblzma / xz
    ["lz4.h"]="-llz4"
    ["lz4frame.h"]="-llz4"
    ["zstd.h"]="-lzstd"
    ["snappy-c.h"]="-lsnappy"
    ["blosc.h"]="-lblosc"
    ["brotli/decode.h"]="-lbrotlidec"
    ["brotli/encode.h"]="-lbrotlienc"
    ["archive.h"]="-larchive"                      # libarchive — tar/zip/etc.
    ["zip.h"]="-lzip"                              # libzip

    # -----------------------------------------------------------------------
    # M. CRYPTOGRAPHY & HASHING
    # -----------------------------------------------------------------------
    ["openssl/ssl.h"]="-lssl -lcrypto"
    ["openssl/crypto.h"]="-lcrypto"
    ["openssl/sha.h"]="-lcrypto"
    ["openssl/evp.h"]="-lcrypto"
    ["openssl/rsa.h"]="-lcrypto"
    ["openssl/aes.h"]="-lcrypto"
    ["openssl/hmac.h"]="-lcrypto"
    ["gnutls/gnutls.h"]="-lgnutls"
    ["nettle/sha2.h"]="-lnettle"
    ["nettle/aes.h"]="-lnettle"
    ["nettle/hmac.h"]="-lhogweed -lnettle -lgmp"
    ["gcrypt.h"]="-lgcrypt -lgpg-error"
    ["sodium.h"]="-lsodium"                        # libsodium — modern crypto
    ["blake3.h"]="-lblake3"
    ["xxhash.h"]="-lxxhash"
    ["b2/blake2.h"]="-lb2"

    # -----------------------------------------------------------------------
    # N. STRING HANDLING & UNICODE
    # -----------------------------------------------------------------------
    ["unicode/ustring.h"]="-licuuc -licudata"      # ICU — Unicode
    ["unicode/ucol.h"]="-licui18n -licuuc -licudata"
    ["pcre.h"]="-lpcre"                            # PCRE — Perl-compatible regex
    ["pcre2.h"]="-lpcre2-8"
    ["regex.h"]=""                                  # POSIX regex — libc
    ["tre/tre.h"]="-ltre"                          # TRE — approximate regex
    ["oniguruma.h"]="-lonig"                       # Oniguruma regex
    ["glib-2.0/glib.h"]="-lglib-2.0"              # GLib strings/containers
    ["iconv.h"]=""                                  # iconv — libc on Linux

    # -----------------------------------------------------------------------
    # O. DATE & TIME
    # -----------------------------------------------------------------------
    ["time.h"]=""                                   # libc
    ["sys/time.h"]=""
    ["tz.h"]="-ltz"                                # IANA timezone (zdump)
    ["howard_hinnant/date/date.h"]=""              # C++ — skip
    ["cctz/civil_time.h"]=""                       # C++ — skip

    # -----------------------------------------------------------------------
    # P. TERMINAL & UI
    # -----------------------------------------------------------------------
    ["ncurses.h"]="-lncurses"
    ["curses.h"]="-lcurses"
    ["panel.h"]="-lpanel -lncurses"
    ["form.h"]="-lform -lncurses"
    ["menu.h"]="-lmenu -lncurses"
    ["readline/readline.h"]="-lreadline"
    ["histedit.h"]="-ledit"                        # libedit (BSD readline)
    ["termios.h"]=""                                # POSIX — libc

    # -----------------------------------------------------------------------
    # Q. GRAPHICS & IMAGE
    # -----------------------------------------------------------------------
    ["GL/gl.h"]="-lGL"
    ["GL/glu.h"]="-lGLU"
    ["GL/glew.h"]="-lGLEW -lGL"
    ["GL/glut.h"]="-lglut -lGL -lGLU"
    ["GLFW/glfw3.h"]="-lglfw -lGL -lm"
    ["vulkan/vulkan.h"]="-lvulkan"
    ["png.h"]="-lpng -lz -lm"
    ["jpeglib.h"]="-ljpeg"
    ["tiff.h"]="-ltiff"
    ["webp/decode.h"]="-lwebp"
    ["webp/encode.h"]="-lwebp"
    ["FreeImage.h"]="-lFreeImage"
    ["cairo/cairo.h"]="-lcairo"
    ["pango/pango.h"]="-lpango-1.0 -lglib-2.0"
    ["rsvg.h"]="-lrsvg-2 -lcairo -lglib-2.0"
    ["MagickCore/MagickCore.h"]="-lMagickCore-7.Q16"  # ImageMagick
    ["plplot/plplot.h"]="-lplplot -lm"             # PLplot — scientific plotting
    ["gnuplot_i.h"]="-lm"                          # gnuplot_i (pipe interface)

    # -----------------------------------------------------------------------
    # R. AUDIO
    # -----------------------------------------------------------------------
    ["portaudio.h"]="-lportaudio -lm"
    ["sndfile.h"]="-lsndfile"
    ["ao/ao.h"]="-lao"
    ["mpg123.h"]="-lmpg123"
    ["vorbis/vorbisfile.h"]="-lvorbisfile -lvorbis -logg"
    ["FLAC/stream_decoder.h"]="-lFLAC"
    ["opus/opus.h"]="-lopus -lm"
    ["fftw3.h"]="-lfftw3 -lm"                     # already above; duplicate suppressed by bash

    # -----------------------------------------------------------------------
    # S. DATABASE
    # -----------------------------------------------------------------------
    ["sqlite3.h"]="-lsqlite3"
    ["postgresql/libpq-fe.h"]="-lpq"
    ["libpq-fe.h"]="-lpq"                          # alternate include path
    ["mysql/mysql.h"]="-lmysqlclient -lm"
    ["mariadb/mysql.h"]="-lmariadb"
    ["mongoc/mongoc.h"]="-lmongoc-1.0 -lbson-1.0"
    ["bson/bson.h"]="-lbson-1.0"
    ["lmdb.h"]="-llmdb"                            # Lightning MDB (key-value)
    ["leveldb/c.h"]="-lleveldb"
    ["rocksdb/c.h"]="-lrocksdb"
    ["redis/hiredis.h"]="-lhiredis"
    ["hiredis/hiredis.h"]="-lhiredis"

    # -----------------------------------------------------------------------
    # T. PARALLELISM & CONCURRENCY
    # -----------------------------------------------------------------------
    # OpenMP — handled by gcc -fopenmp flag, not -l; user adds via CFLAGS
    ["omp.h"]=""                                    # flag: -fopenmp (not -l)
    ["mpi.h"]="-lmpi"                              # OpenMPI / MPICH
    ["mpi/mpi.h"]="-lmpi"
    ["opencl/opencl.h"]="-lOpenCL"
    ["CL/cl.h"]="-lOpenCL"
    ["cuda_runtime.h"]="-lcudart"                  # CUDA runtime
    ["cublas_v2.h"]="-lcublas"                     # cuBLAS
    ["cusolver.h"]="-lcusolver"                    # cuSOLVER
    ["cusparse.h"]="-lcusparse"                    # cuSPARSE
    ["tbb/tbb.h"]="-ltbb"                          # Intel TBB
    ["cilk/cilk.h"]=""                             # Cilk — compiler-intrinsic
    ["dispatch/dispatch.h"]="-ldispatch"           # GCD (macOS/Linux)
    ["ucontext.h"]=""                              # POSIX — libc
    ["taskflow/taskflow.hpp"]=""                   # C++ — skip

    # -----------------------------------------------------------------------
    # U. DEBUGGING & PROFILING
    # -----------------------------------------------------------------------
    ["valgrind/valgrind.h"]=""                     # header-only annotations
    ["valgrind/memcheck.h"]=""
    ["gperftools/profiler.h"]="-lprofiler"
    ["gperftools/heap-profiler.h"]="-ltcmalloc"
    ["jemalloc/jemalloc.h"]="-ljemalloc"
    ["mimalloc.h"]="-lmimalloc"
    ["sanitizer/asan_interface.h"]=""              # compiler-intrinsic
    ["backtrace.h"]="-lbacktrace"
    ["execinfo.h"]=""                              # POSIX — libc (backtrace())
    ["elfutils/libdw.h"]="-ldw"
    ["libunwind.h"]="-lunwind"
    ["bfd.h"]="-lbfd -liberty"

    # -----------------------------------------------------------------------
    # V. PORTABILITY / UTILITY
    # -----------------------------------------------------------------------
    ["glib-2.0/glib/ghash.h"]="-lglib-2.0"
    ["glib-2.0/glib/glist.h"]="-lglib-2.0"
    ["gio/gio.h"]="-lgio-2.0 -lgobject-2.0 -lglib-2.0"
    ["gobject/gobject.h"]="-lgobject-2.0 -lglib-2.0"
    ["cunit/CUnit.h"]="-lcunit"                    # CUnit testing
    ["check.h"]="-lcheck -lpthread -lm"            # Check unit testing
    ["criterion/criterion.h"]="-lcriterion"        # Criterion testing
    ["cmocka.h"]="-lcmocka"                        # CMocka (mock testing)
    ["unity.h"]="-lm"                              # Unity (embedded testing)
    ["uthash.h"]=""                                # header-only hash table
    ["utlist.h"]=""                                # header-only linked list
    ["utarray.h"]=""                               # header-only dynamic array
    ["c-algorithms/list.h"]="-lc-algorithms"
    ["gc.h"]="-lgc"                                # Boehm garbage collector
    ["talloc.h"]="-ltalloc"                        # hierarchical allocator (Samba)
    ["apr-1/apr_general.h"]="-lapr-1"             # Apache Portable Runtime
    ["cffi.h"]="-lffi"                             # libffi — foreign function interface
    ["ffi.h"]="-lffi"
    ["lua.h"]="-llua -lm -ldl"                    # Lua scripting
    ["lauxlib.h"]="-llua -lm -ldl"
    ["python3.11/Python.h"]="-lpython3.11 -lm -ldl"  # Python embedding
    ["python3.12/Python.h"]="-lpython3.12 -lm -ldl"
    ["tcl.h"]="-ltcl"
    ["guile/guile.h"]="-lguile-3.0 -lgc -lm"
    ["libconfig.h"]="-lconfig"                     # libconfig — config files
    ["ini.h"]="-lm"                                # inih (header-only ini)
    ["argp.h"]=""                                  # POSIX argument parsing — libc
    ["popt.h"]="-lpopt"
    ["cargs.h"]="-lcargs"
    ["linenoise.h"]="-lm"                          # linenoise (header-heavy)

)

# --- 3. Scan .ver source and collect flags ---------------------------------

declare -A seen_flags   # deduplicate
linker_flags=()

for header in "${!LIB_MAP[@]}"; do
    flag_str="${LIB_MAP[$header]}"
    [[ -z "$flag_str" ]] && continue   # no flag needed for this header

    if grep -qF "Include the library '${header}'" "${filename}.ver" || \
       grep -qF "Include the header '${header}'" "${filename}.ver"; then
        # Split the (possibly multi-flag) string into individual tokens
        read -ra tokens <<< "$flag_str"
        for tok in "${tokens[@]}"; do
            if [[ -z "${seen_flags[$tok]+set}" ]]; then
                seen_flags[$tok]=1
                linker_flags+=("$tok")
            fi
        done
    fi
done

# --- 4. Compile ------------------------------------------------------------

echo "gcc linker flags: ${linker_flags[*]:-<none>}"
gcc -o "${filename}" "${filename}.c" compiler/runtime.c "${linker_flags[@]+"${linker_flags[@]}"}"

# --- 5. Clean up intermediate C file (uncomment to enable) ----------------
#rm "${filename}.c"