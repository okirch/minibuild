#
# python specific portions of brcoti
#
#   Copyright (C) 2020 Olaf Kirch <okir@suse.de>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

import sys
import os
import os.path
import io
import pkginfo
import glob
import shutil

import brcoti_core

def getinfo_pkginfo(path):

	if path.endswith(".whl"):
		return pkginfo.Wheel(path)

	if os.path.isdir(path):
		return pkginfo.UnpackedSDist(path)

	return pkginfo.SDist(path)
	
def getinfo_setuptools(path):
	path = os.path.join(path, 'setup.py')
	if not os.path.exists(path):
		return None

	setup_args = None

	def my_setup(**kwargs):
		nonlocal setup_args
		setup_args = kwargs

	import setuptools

	setuptools.setup = my_setup

	import importlib.util
	spec = importlib.util.spec_from_file_location('setup', path)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)

	print("setup() called with args", setup_args.keys())

	mapping = {
		'author' : 'author',
		'author_email' : 'author_email',
		'classifiers' : 'classifiers',
		'keywords' : 'keywords',
		'license' : 'license',
		'url' : 'home_page',
		'description' : 'summary',
		'long_description' : 'description',
		'long_description_content_type' : 'description_content_type',

		'python_requires' : 'requires_python',
		'setup_requires' : 'requires',
		# 'tests_require' : 'requires',
		# 'extras_require' : 'requires'
	}

	d = pkginfo.Distribution()
	for (key, attr) in mapping.items():
		value = setup_args.get(key)
		if value:
			existing = getattr(d, attr, None)
			if existing is not None:
				if type(existing) == list or type(value) == list:
					value = list(existing) + list(value)
				else:
					value = existing + value
			setattr(d, attr, value)

	return d

def pkginfo_as_dict(pkg):
	attrs = []
	for a in dir(pkg):
		if not a.startswith("_"):
			attrs.append(a)

	result = dict()
	for k in attrs:
		v = getattr(pkg, k, None)
		if v is None:
			continue
		if callable(v):
			continue
		result[k] = v

	return result

def pkginfo_print(pkg):
	attrs = []
	for a in dir(pkg):
		if not a.startswith("_"):
			attrs.append(a)

	for k in attrs:
		v = getattr(pkg, k, None)
		if v is None:
			continue
		if callable(v):
			continue

		k = k.capitalize() + ":"
		if type(v) not in (tuple, list):
			v = repr(v)
			if len(v) > 100:
				v = v[:100] + "..."
			print("%-20s  %s" % (k, v))
		elif len(v) == 0:
			# print("%-20s  %s" % (k, "<empty>"))
			continue
		else:
			print("%s" % (k))
			for vi in v:
				print("        %s" % vi)

def pkginfo_as_metadata(pkg):
	def name_to_header(s):
		# strip off trailing plural "s"
		if s in ('classifiers', 'supported_platforms', 'project_urls'):
			s = s[:-1]
		s = (n.capitalize() for n in s.split('_'))
		return "-".join(s)

	def maybe_print(key):
		nonlocal info
		nonlocal seen

		header = name_to_header(key)
		seen.add(key)

		res = header + ": "

		value = info.get(key)
		if value is None:
			return ""

		if type(value) not in (tuple, list):
			if type(value) != str:
				value = repr(value)

			if '\n' in value:
				res += "\n        ".join(value.split('\n'))
			else:
				res += value
		else:
			# Turn classifiers list into several "Classifier:" header lines
			if "Url" in header:
				header = header.replace('Url', "URL")

			res = "\n".join("%s: %s" % (header, v) for v in value)

		if res:
			res += "\n"
			# print(">> %s" % res)
		return res

	seen = set()
	first = ('metadata_version', 'name', 'version', 'summary', 'home_page', 'author', 'author_email', 'maintainer', 'maintainer_email', 'license')
	ignore = ('filename', 'description', 'description_content_type')

	info = pkginfo_as_dict(pkg)

	result = ""
	for key in first:
		result += maybe_print(key)

	for key in sorted(info.keys()):
		if key in seen or key in ignore:
			continue
		result += maybe_print(key)

	result += maybe_print('description_content_type')

	if pkg.description:
		result += "\n" + pkg.description

	return result

def get_python_version():
	vi = sys.version_info
	return "%d.%d.%d" % (vi.major, vi.minor, vi.micro)

def canonical_package_name(name):
	return name.replace('_', '-')

class PythonBuildInfo(brcoti_core.PackageBuildInfo):
	def __init__(self, name, version = None, type = None):
		super(PythonBuildInfo, self).__init__(canonical_package_name(name), version)

		self.type = type
		self.requires_python = None

		self.fullreq = None
		self.filename = None

		# package info
		self.home_page = None
		self.author = None

	def id(self):
		if not self.version:
			return self.name
		return "%s-%s" % (self.name, self.version)

	def update_hash(self, algo):
		import hashlib

		m = hashlib.new(algo)
		with open(self.local_path, "rb") as f:
			m.update(f.read())

		self.add_hash(algo, m.hexdigest())

	def git_url(self):
		url = self.home_page
		if not url:
			return None

		url = url.replace('_', '-')
		if not url or not "github.com" in url:
			print("WARNING: Package homepage \"%s\" doesn't look like a git repo" % url)
			return None

		return url

	@property
	def is_source(self):
		return self.type == 'sdist'

	def verify_requires_python(self):
		# We could also use Marker('python_version %s').evaluate()
		from packaging.specifiers import SpecifierSet, InvalidSpecifier

		requires_python = self.requires_python
		if requires_python is None:
			return True

		try:
			spec = SpecifierSet(requires_python, prereleases = False)
		except InvalidSpecifier:
			print("Warning: %s has invalid requires_python specifier \"%s\"" % (self.id(), requires_python))
			return False

		return get_python_version() in spec

	@staticmethod
	def parse_filename(filename):
		def split_suffix(name):
			if name.endswith(".tar.gz"):
				k = -7
			elif name.endswith(".tar.bz2"):
				k = -8
			else:
				k = name.rindex('.')
			suffix = name[k+1:]
			name = name[:k]
			return name, suffix

		def split_version(name):
			components = name.split('-')
			nlist = []
			while components:
				c = components[0]
				if c[0].isdigit():
					break
				nlist.append(c)
				del components[0]

			name = "-".join(nlist)
			version = "-".join(components)
			return name, version

		# First, separate the suffix from the file name
		_name, _suffix = split_suffix(filename)

		# Then, split the name into package name and version.
		# Things get a bit hairy because we need to deal with
		# weirdo names like jedi-0.8.0-final0
		_name, _version = split_version(_name)

		if _suffix in ("tar.gz", "tar.bz2", "zip"):
			_type = 'sdist'
		elif _suffix == "whl":
			# Remove the "py*-platform-arch" stuff from the version string
			# FIXME: we should really return this information
			_version = "-".join(_version.split("-")[:-3])
			_type = 'bdist_wheel'
		elif _suffix == "egg":
			_version = "-".join(_version.split("-")[:-1])
			_type = 'bdist_egg'
		elif _suffix == "rpm":
			# ipython and others distribute rpms via pypi
			# split before the RPM arch specifier
			k = _version.rindex('.')
			_version = _version[:k]
			_type = "rpm"
		elif _suffix == "exe":
			# Not sure if there's a standard naming scheme for windows executables
			# Remove ".win-bla-somthing" if we find it
			k = _version.find(".win")
			if k > 0:
				_version = _version[:k]
			else:
				k = _version.find(".py")
				if k > 0:
					_version = _version[:k]
			_type = "exe"
		else:
			raise ValueError("Unable to parse file name \"%s\"" % filename)

		return _name, _version, _type

	@staticmethod
	def from_local_file(path, name = None, version = None, type = None):
		filename = os.path.basename(path)

		if not name or not version or not type:
			# try to detect version and type by looking at the file name
			_name, _version, _type = PythonBuildInfo.parse_filename(filename)

			if name:
				assert(name == _name)
			name = _name
			if version:
				assert(version == _version)
			version = _version
			if type:
				assert(type == _type)
			type = _type

		build = PythonBuildInfo(name, version, type)
		build.filename = filename
		build.local_path = path

		for algo in PythonEngine.REQUIRED_HASHES:
			build.update_hash(algo)

		return build

class PythonReleaseInfo(brcoti_core.PackageReleaseInfo):
	def __init__(self, name, version, parsed_version = None):
		super(PythonReleaseInfo, self).__init__(canonical_package_name(name), version)

		if not parsed_version:
			from packaging.specifiers import parse
			parsed_version = parse(version)

		self.parsed_version = parsed_version

	def id(self):
		return "%s-%s" % (self.name, self.version)

	def more_recent_than(self, other):
		assert(isinstance(other, PythonReleaseInfo))
		return other.parsed_version < this.parsed_version

	def build_types(self):
		return [b.type for b in self.builds]

class PythonPackageInfo(brcoti_core.PackageInfo):
	def __init__(self, name):
		super(PythonPackageInfo, self).__init__(canonical_package_name(name))

class PythonDownloadFinder(brcoti_core.DownloadFinder):
	def __init__(self, req_string, verbose):
		from packaging.requirements import Requirement

		super(PythonDownloadFinder, self).__init__(verbose)
		req = Requirement(req_string)
		self.requirement = req

		self.name = req.name
		self.allow_prereleases = False
		self.request_specifier = req.specifier

	def release_match(self, release):
		assert(release.parsed_version)
		if not self.allow_prereleases and release.parsed_version.is_prerelease:
			return False

		if self.request_specifier and release.parsed_version not in self.request_specifier:
			return False

		return True

	def get_best_match(self, index):
		info = index.get_package_info(self.name)

		if self.verbose:
			print("%s versions: %s" % (self.name, ", ".join(info.versions())))

		best_ver = None
		best_match = None

		for release in info.releases:
			if not self.release_match(release):
				if self.verbose:
					print("ignoring release %s" % release.id())
				continue

			if best_ver and release.parsed_version <= best_ver:
				continue

			for build in release.builds:
				# print("%s: inspecting build %s" % (release.id(), build.filename))
				if self.build_match(build):
					if not build.verify_requires_python():
						if self.verbose:
							print("ignoring build %s (requires python %s)" % (build.filename, build.requires_python))
						continue

					best_match = build
					best_ver = release.parsed_version

		if not best_match:
			raise ValueError("%s: unable to find a release that is compatible with my python version" % self.name)

		if self.verbose:
			print("Using %s" % best_match.id())

		return best_match

class PythonSourceDownloadFinder(PythonDownloadFinder):
	def __init__(self, req_string, verbose = False):
		super(PythonSourceDownloadFinder, self).__init__(req_string, verbose)

	def build_match(self, build):
		# print("inspecting %s which is of type %s" % (build.filename, build.type))
		return build.type == 'sdist'

class PythonBinaryDownloadFinder(PythonDownloadFinder):
	def __init__(self, req_string, verbose = False):
		super(PythonBinaryDownloadFinder, self).__init__(req_string, verbose)

	def build_match(self, build):
		# print("inspecting %s which is of type %s" % (build.filename, build.type))
		return build.type == 'bdist_wheel'

class JSONPackageIndex(brcoti_core.HTTPPackageIndex):
	def __init__(self, url = 'https://pypi.org/pypi'):
		super(JSONPackageIndex, self).__init__(url)
		self._pkg_url_template = "{index_url}/{pkg_name}/json"

	# JSON contains
	# ['info', 'last_serial', 'releases', 'urls']
	# info is a dict of PKG-INFO stuff
	# last_serial is an int, not sure what for
	def process_package_info(self, name, resp):
		from packaging.specifiers import parse
		import json

		info = PythonPackageInfo(name)

		d = json.load(resp)
		print(d['info'].keys())

		ji = d['info']
		info.home_page = ji['home_page']
		info.author = ji['author']
		print("home page is", info.home_page)

		for (ver, files) in d['releases'].items():
			relInfo = PythonReleaseInfo(name, ver)
			info.add_release(relInfo)

			for download in files:
				filename = download['filename']

				if download['yanked']:
					print("Ignoring %s: yanked (%s)" % (filename, download['yanked_reason']))
					continue

				type = download['packagetype']
				if type == 'sdist':
					if download['python_version'] != 'source':
						raise ValueError("%s: unable to deal with sdist package w/ version \"%s\"" % (download['filename'], download['python_version']))
					pkgInfo = PythonBuildInfo(name, ver, type = type)
				elif type.startswith('bdist'):
					pkgInfo = PythonBuildInfo(name, ver, type = type)
				else:
					print("%s: don't know how to deal with package type \"%s\"" % (filename, type))
					continue

				pkgInfo.filename = filename
				pkgInfo.url = download['url']
				pkgInfo.requires_python = download['requires_python']

				md = download.get('md5_digest')
				if md:
					pkgInfo.add_hash('md5', md)
				for algo, md in download['digests'].items():
					pkgInfo.add_hash(algo, md)

				relInfo.add_build(pkgInfo)

		return info

class SimplePackageIndex(brcoti_core.HTTPPackageIndex):
	def __init__(self, url):
		super(SimplePackageIndex, self).__init__(url)

		# The trailing / is actually important, because otherwise
		# urljoin(base_url, "../../packages/blah/fasel")
		# will not do the right thing
		self._pkg_url_template = "{index_url}/simple/{pkg_name}/"

	# HTML response contains
	# <head>...
	#  <meta name="api-version" value="2"/>
	# </head>
	# <body><h1>Links for flit</h1>
        # <a href="../../packages/flit/0.1/$filename#sha256=$hexdigest" rel="internal" data-requires-python="3" >$filename</a><br/>
	# ...
	def process_package_info(self, name, resp):
		import xml.etree.ElementTree as ET
		tree = ET.parse(resp)
		root = tree.getroot()

		info = None
		if root.tag == 'html':
			for node in root:
				if node.tag == 'head':
					self.process_html_head(node)
				elif node.tag == 'body':
					if info:
						raise ValueError("Server response contains several <body> elements")
					info = self.process_html_body(resp.url, node)
		else:
			info = self.process_html_body(resp.url, root)

		if not info:
			raise ValueError("Server response lacks a <body> element")

		return info

	def process_html_head(self, node):
		for m in node.findall('meta'):
			name = m.attrib.get('name')
			if name != 'api-version':
				continue

			value = m.attrib.get('value')
			if value != '2':
				raise ValueError("Unable to deal with pypi simple index API version %s" % value)

			# print("Found API version %s; good" % value)

		# all is well

	def process_html_body(self, request_url, node):
		builds = []

		for anchor in node.findall(".//a"):
			build = self.process_html_a(request_url, anchor)
			if build:
				builds.append(build)

		if not builds:
			raise ValueError("No <a> elements found in server response - package not found")

		name = builds[0].name.lower()
		for b in builds:
			if b.name.lower() != name:
				raise ValueError("Server response contains a mix of packages (%s and %s)" % (name, b.name))

		releases = dict()
		for b in builds:
			r = releases.get(b.version)
			if not r:
				r = PythonReleaseInfo(name, b.version)
				releases[r.version] = r

			r.add_build(b)

		info = PythonPackageInfo(name)
		for release in sorted(releases.values(), key = lambda r: r.parsed_version):
			info.add_release(release)

		return info

	def process_html_a(self, request_url, anchor):
		from urllib.parse import urljoin, urldefrag

		rel = anchor.attrib.get('rel')
		if rel != "internal":
			print("IGNORING anchor with rel=%s" % rel)
			return None

		href = anchor.attrib['href']
		href, hash = urldefrag(href)

		# FIXME: this only works on systems that use '/' as the path separator
		filename = os.path.basename(href)
		assert(filename == anchor.text)

		try:
			name, version, type = PythonBuildInfo.parse_filename(filename)
			# print("%s => (\"%s\", \"%s\", \"%s\")" % (filename, name, version, type))
		except ValueError:
			print("WARNING: Unable to parse filename \"%s\" in SimpleIndex response" % filename)
			return None

		if type == 'rpm' or type == 'exe':
			return None

		build = PythonBuildInfo(name, version, type)
		build.filename = filename

		build.url = urljoin(request_url, href)
		# print("%s plus %s -> %s" % (request_url, href, build.url))

		rpy = anchor.attrib.get('data-requires-python')
		if rpy:
			build.requires_python = rpy

		if hash:
			algo, md = hash.split('=')
			build.add_hash(algo, md)

		return build


# Upload package using twine
class PythonUploader(brcoti_core.Uploader):
	def __init__(self, repo):
		self.repo = repo

	def describe(self):
		return "Python repository \"%s\"" % self.repo

	def upload(self, build):
		assert(build.local_path)

		print("Uploading %s to %s repository" % (build.local_path, self.repo))
		cmd = "twine upload --verbose "
		cmd += " --disable-progress-bar"
		cmd += " --repository %s %s" % (self.repo, build.local_path)

		brcoti_core.run_command(cmd)

class WheelArchive(object):
	def __init__(self, path):
		self.path = path
		self._zip = self.open()

	def open(self):
		import zipfile

		return zipfile.ZipFile(self.path, mode = 'r')

	@property
	def basename(self):
		return os.path.basename(self.path)

	def name_set(self):
		result = set()
		for member in self._zip.infolist():
			if member.is_dir():
				continue

			result.add(member.filename)

		return result

	def compare(self, other):
		my_name_set = self.name_set()
		other_name_set = other.name_set()

		added_set = other_name_set - my_name_set
		removed_set = my_name_set - other_name_set

		changed_set = set()
		for member_name in my_name_set.intersection(other_name_set):
			my_data = self._zip.read(member_name)
			other_data = other._zip.read(member_name)

			if other_data != my_data:
				changed_set.add(member_name)

		if False:
			print("added=" + ", ".join(added_set))
			print("removed=" + ", ".join(removed_set))
			print("changed=" + ", ".join(changed_set))

		return added_set, removed_set, changed_set

class PythonBuildDirectory(brcoti_core.BuildDirectory):
	def __init__(self, compute, build_base):
		super(PythonBuildDirectory, self).__init__(compute, build_base)

	# Most of the unpacking happens in the BuildDirectory base class.
	# The only python specific piece is guessing which directory an archive is extracted to
	def archive_get_unpack_directory(self, sdist):
		name, version, type = PythonBuildInfo.parse_filename(sdist.local_path)
		return name + "-" + version

	def build(self, quiet = False):
		assert(self.directory)
		sdist = self.sdist

		cmd = "python3 setup.py bdist_wheel"
		cmd = "pip3 wheel --wheel-dir dist ."
		cmd += " --log pip.log"
		cmd += " --no-deps"

		if self.quiet:
			cmd += " >build.log 2>&1"
		else:
			cmd += " 2>&1 | tee build.log"

		self.compute.run_command(cmd, working_dir = self.directory)

		# glob_files returns a list of ComputeResource* objects
		wheels = self.directory.glob_files(os.path.join("dist", "*.whl"))

		print("Successfully built %s: %s" % (sdist.id(), ", ".join([w.basename() for w in wheels])))
		for w in wheels:
			w = w.hostpath()

			build = PythonBuildInfo.from_local_file(w)

			for algo in PythonEngine.REQUIRED_HASHES:
				build.update_hash(algo)

			self.artefacts.append(build)

		return self.artefacts

	def compare_build_artefacts(self, old_path, new_path):
		return WheelArchive(old_path).compare(WheelArchive(new_path))

	# Detect build requirements by parsing the pip.log file.
	# There must be a smarter way to extract the build requirements than
	# this...
	#
	# Note: this approach currently covers /all/ build requirements, direct
	# as well as expanded. For instance, gri requires setuptools_scm, which
	# in turn has a "requires-dist: toml; extra = 'toml'" in its metadata.
	# This will also show up in pip.log as pip tries to install all
	# required dependencies.
	def guess_build_dependencies(self):
		from packaging.requirements import Requirement
		import re

		logfile = self.directory.lookup("pip.log")
		if logfile is None:
			print("No pip.log found... expect problems")
			return

		print("Parsing pip.log")
		req = None

		self.build_requires = []
		with logfile.open() as f:
			for l in f.readlines():
				# Parse lines like:
				# Added flit_core<4,>=3.0.0 from http://.../flit_core-3.0.0-py3-none-any.whl#md5=7648384867c294a95487e26bc451482d to build tracker
				if req and ('Added' in l) and ('to build tracker' in l):
					from urllib.parse import urldefrag, urlparse

					if " (from " in l:
						# This is a dist requirement expanded from some direct build requirement.
						# We don't do anything special with this for now; we just add it to our
						# published set of build reqs
						pass

					m = re.search('Added (.*) from ([^ ]*)', l)
					if not m:
						print("Tried to match %s - regex failed" % l)
						raise ValueError("regex match failed")

					r = Requirement(m.group(1))
					url = m.group(2)

					# This is needed to deal with some oddities of pip.
					# For instance, package flit requires flit_core. However,
					# pip will change that name to flit-core, and look for it
					# in the index by this name.
					# pypi has both flit_core and flit-core wheels, but they have
					# different hash digests, causing our rebuild checks to
					# fire without need.
					if req.name != r.name:
						r.name = canonical_package_name(r.name)
						assert(req.name == r.name)
					req.fullreq = str(r)

					url, frag = urldefrag(url)
					if frag:
						algo, md = frag.split('=')
						req.add_hash(algo, md)

					req.url = url
					req.filename = os.path.basename(urlparse(url).path)
					continue

				if "to search for versions of" not in l:
					continue

				m = re.search('to search for versions of (.*):', l)
				if not m:
					print("Tried to match %s - regex failed" % l)
					raise ValueError("regex match failed")

				name = m.group(1)
				if name == 'pip':
					# We do not explicitly track dependencies on pip and possibly
					# other packages that are already installed.
					req = None
					continue

				req = PythonBuildInfo(name)
				self.build_requires.append(req)
				if not self.quiet:
					print("Found requirement %s" % req.name)

		for req in self.build_requires:
			if not req.fullreq:
				raise ValueError("pip log parser failed - unable to determine req string for build requirement %s" % req.name)

	def prepare_results(self, build_state):
		self.maybe_save_file(build_state, "build.log")
		self.maybe_save_file(build_state, "pip.log")

		build_state.write_file("build-requires", self.build_requires_as_string())
		build_state.write_file("build-artefacts", self.build_artefacts_as_string())

		for wheel in self.artefacts:
			# Copy the wheel itself
			wheel.local_path = build_state.save_file(wheel.local_path)

			name = "%s-METADATA.txt" % wheel.id()
			pi = getinfo_pkginfo(wheel.local_path)
			build_state.write_file(name,
				pkginfo_as_metadata(pi),
				"%s metadata" % wheel.id())

		# Always upload the source tarball with the build artefacts
		if self.sdist not in self.artefacts:
			self.artefacts.append(self.sdist)

	def build_artefacts_as_string(self):
		b = io.StringIO()
		for wheel in self.artefacts:
			b.write("wheel %s\n" % wheel.name)
			b.write("  version %s\n" % wheel.version)

			for algo in PythonEngine.REQUIRED_HASHES:
				b.write("  hash %s %s\n" % (algo, wheel.hash.get(algo)))
		return b.getvalue()

	def build_requires_as_string(self):
		b = io.StringIO()
		for req in self.build_requires:
			b.write("require %s\n" % req.name)
			if req.fullreq:
				b.write("  specifier %s\n" % req.fullreq);
			if req.hash:
				for (algo, md) in req.hash.items():
					b.write("  hash %s %s\n" % (algo, md))
		return b.getvalue()

	def maybe_save_file(self, build_state, name):
		fh = self.directory.lookup(name)
		if fh is None:
			print("Not saving %s (does not exist)" % name)
			return None

		return build_state.save_file(fh)

	def write_file(self, build_state, name, write_func):
		buffer = io.StringIO()
		write_func(buffer)
		return build_state.write_file(name, buffer.getvalue())

class PythonBuildState(brcoti_core.BuildState):
	def __init__(self, savedir, index):
		super(PythonBuildState, self).__init__(savedir)

		self.index = index

	def build_changed(self, req):
		if req.fullreq:
			finder = PythonBinaryDownloadFinder(req.fullreq)
		else:
			finder = PythonBinaryDownloadFinder(req.name)

		print("Build requires %s" % (finder.requirement))

		p = finder.get_best_match(self.index)

		print("  Best match available from package index: %s" % p.filename)
		if req.version:
			if req.version != p.version:
				print("Building would pick %s-%s rather than %s-%s" % (
					p.name, p.version,
					req.name, req.version))
				return True

		match = False
		for algo, md in req.hash.items():
			print("  We are looking for %s %s %s" % (req.id(), algo, md))
			have_md = p.hash.get(algo)
			if have_md is None:
				print("  => index does not provide %s hash for %s" % (algo, p.filename))
				continue

			print("  => index provides %s %s %s" % (p.filename, algo, p.hash.get(algo)))
			if have_md == md:
				match = True

		if not match:
			print("%s was apparently rebuilt in the meantime, we need to rebuild" % p.filename)
			return True

		print("Build requirement did not change")

	def create_empty_requires(self, name):
		return PythonBuildInfo(name)

class PythonEngine(brcoti_core.Engine):
	REQUIRED_HASHES = ('md5', 'sha256')

	def __init__(self, compute_backend, opts):
		compute = compute_backend.spawn("python3")

		super(PythonEngine, self).__init__("python", compute, opts)

		if True:
			index_url = 'http://localhost:8081/repository/pypi-group/'
			packageIndex = SimplePackageIndex(url = index_url)
		else:
			packageIndex = JSONPackageIndex()

		self.prefer_git = opts.git

		self.index = packageIndex

		self.downloader = brcoti_core.Downloader()

		if opts.upload_to:
			self.uploader = PythonUploader(opts.upload_to)

	def build_info_from_local_file(self, path):
		return PythonBuildInfo.from_local_file(file)

	def build_source_locate(self, req_string, verbose = True):
		finder = PythonSourceDownloadFinder(req_string, verbose)
		return finder.get_best_match(self.index)

	def build_state_factory(self, sdist):
		savedir = self.build_state_path(sdist.id())
		return PythonBuildState(savedir, self.index)

	def build_unpack(self, sdist):
		bd = PythonBuildDirectory(self.compute, self.build_dir)
		if self.prefer_git:
			bd.unpack_git(sdist, sdist.id())
		else:
			bd.unpack_archive(sdist)

		print("Unpacked %s to %s" % (sdist.id(), bd.unpacked_dir()))
		return bd

	def resolve_build_req(self, req):
		req_string = req.fullreq
		if not req_string:
			req_string = req.name
			if req.version:
				req_string += "==" + req.version
		assert(req_string)
		finder = PythonBinaryDownloadFinder(req_string)
		return finder.get_best_match(self.index)

def engine_factory(compute, opts):
	return PythonEngine(compute, opts)
