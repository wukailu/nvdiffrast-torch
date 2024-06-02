# Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import nvdiffrast
import setuptools
import os
import logging
from torch.utils.cpp_extension import BuildExtension, CUDAExtension, include_paths

ext_modules = []

def make_extension(gl):
	assert isinstance(gl, bool)

	# Make sure we can find the necessary compiler and libary binaries.
	if os.name == 'nt':
		lib_dir = os.path.dirname(__file__) + r"\..\lib"
		def find_cl_path():
			import glob
			for edition in ['Enterprise', 'Professional', 'BuildTools', 'Community']:
				vs_relative_path = r"\Microsoft Visual Studio\*\%s\VC\Tools\MSVC\*\bin\Hostx64\x64" % edition
				paths = sorted(glob.glob(r"C:\Program Files" + vs_relative_path), reverse=True)
				paths += sorted(glob.glob(r"C:\Program Files (x86)" + vs_relative_path), reverse=True)
				if paths:
					return paths[0]

		# If cl.exe is not on path, try to find it.
		if os.system("where cl.exe >nul 2>nul") != 0:
			cl_path = find_cl_path()
			if cl_path is None:
				raise RuntimeError("Could not locate a supported Microsoft Visual C++ installation")
			os.environ['PATH'] += ';' + cl_path

	# Compiler options.
	opts = ['-DNVDR_TORCH']

	# Linker options for the GL-interfacing plugin.
	ldflags = []
	if gl:
		if os.name == 'posix':
			ldflags = ['-lGL', '-lEGL']
		elif os.name == 'nt':
			libs = ['gdi32', 'opengl32', 'user32', 'setgpu']
			ldflags = ['/LIBPATH:' + lib_dir] + ['/DEFAULTLIB:' + x for x in libs]

	# 请注意， setuptools 无法处理 具有相同名称但扩展名不同的文件，因此，如果您使用 setup.py 方法而不是 JIT 方法，则必须为您的 CUDA 文件指定不同的名称 而不是 C++ 文件的名称(对于 JIT 方法， lltm.cpp 和 lltm.cu 可以正常工作)。
	# List of source files.
	if gl:
		source_files = [
			'../common/common.cpp',
			'../common/glutil.cpp',
			'../common/rasterize_gl.cpp',
			'torch_bindings_gl.cpp',
			'torch_rasterize_gl.cpp',
		]
	else:
		source_files = [
			'../common/cudaraster/impl/Buffer.cpp',
			'../common/cudaraster/impl/CudaRaster.cpp',
			'../common/cudaraster/impl/RasterImpl_kernel.cu',	# renamed
			'../common/cudaraster/impl/RasterImpl.cpp',
			'../common/common.cpp',
			'../common/rasterize.cu',
			'../common/interpolate.cu',
			'../common/texture_kernel.cu',	# renamed
			'../common/texture.cpp',
			'../common/antialias.cu',
			'torch_bindings.cpp',
			'torch_rasterize.cpp',
			'torch_interpolate.cpp',
			'torch_texture.cpp',
			'torch_antialias.cpp',
		]

	# compile for RTX30xx+
	os.environ["TORCH_CUDA_ARCH_LIST"] = "8.0 8.6 8.7 8.9 9.0"

	# On Linux, show a warning if GLEW is being forcibly loaded when compiling the GL plugin.
	if gl and (os.name == 'posix') and ('libGLEW' in os.environ.get('LD_PRELOAD', '')):
		logging.getLogger('nvdiffrast').warning("Warning: libGLEW is being loaded via LD_PRELOAD, and will probably conflict with the OpenGL plugin")

	# Try to detect if a stray lock file is left in cache directory and show a warning. This sometimes happens on Windows if the build is interrupted at just the right moment.
	plugin_name = 'nvdiffrast_plugin' + ('_gl' if gl else '')

	# Speed up compilation on Windows.
	if os.name == 'nt':
		# Skip telemetry sending step in vcvarsall.bat
		os.environ['VSCMD_SKIP_SENDTELEMETRY'] = '1'

		# Opportunistically patch distutils to cache MSVC environments.
		try:
			import distutils._msvccompiler
			import functools
			if not hasattr(distutils._msvccompiler._get_vc_env, '__wrapped__'):
				distutils._msvccompiler._get_vc_env = functools.lru_cache()(distutils._msvccompiler._get_vc_env)
		except:
			pass

	# Compile and load.
	source_paths = [os.path.join("nvdiffrast/torch", fn) for fn in source_files]
	ext = CUDAExtension(
		name=plugin_name,
		sources=source_paths,
		extra_link_args=ldflags,
		extra_compile_args={"cxx": opts, "nvcc": opts+['-lineinfo']},
	)
	return ext

ext_modules = [make_extension(gl) for gl in [True, False]]

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="nvdiffrast",
    version=nvdiffrast.__version__,
    author="Samuli Laine",
    author_email="slaine@nvidia.com",
    description="nvdiffrast - modular primitives for high-performance differentiable rendering",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/NVlabs/nvdiffrast",
    packages=setuptools.find_packages(),
    package_data={
        'nvdiffrast': [
            'common/*.h',
            'common/*.inl',
            'common/*.cu',
            'common/*.cpp',
            'common/cudaraster/*.hpp',
            'common/cudaraster/impl/*.cpp',
            'common/cudaraster/impl/*.hpp',
            'common/cudaraster/impl/*.inl',
            'common/cudaraster/impl/*.cu',
            'lib/*.h',
            'torch/*.h',
            'torch/*.inl',
            'torch/*.cpp',
            'tensorflow/*.cu',
        ] + (['lib/*.lib'] if os.name == 'nt' else [])
    },
    include_package_data=True,
    install_requires=['numpy'],  # note: can't require torch here as it will install torch even for a TensorFlow container
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
	zip_safe=False,
	ext_modules=ext_modules,
	cmdclass={"build_ext": BuildExtension},
)
