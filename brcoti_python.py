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

ENGINE_NAME	= 'python'

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

class PythonBuildRequirement(brcoti_core.BuildRequirement):
	engine = ENGINE_NAME

	def __init__(self, name, req_string = None, cooked_requirement = None):
		super(PythonBuildRequirement, self).__init__(canonical_package_name(name), req_string, cooked_requirement)

	def parse_requirement(self, req_string):
		from packaging.requirements import Requirement

		self.cooked_requirement = Requirement(req_string)
		self.req_string = req_string

	@staticmethod
	def from_string(req_string):
		from packaging.requirements import Requirement

		cooked_requirement = Requirement(req_string)
		return PythonBuildRequirement(cooked_requirement.name, req_string, cooked_requirement)

	def __repr__(self):
		if self.cooked_requirement:
			return str(self.cooked_requirement)

		return super(PythonBuildRequirement, self).__repr__()

class PythonArtefact(brcoti_core.Artefact):
	engine = ENGINE_NAME

	def __init__(self, name, version = None, type = None):
		super(PythonArtefact, self).__init__(canonical_package_name(name), version)

		self.type = type
		self.requires_python = None

		self.filename = None

		# package info
		self.home_page = None
		self.author = None

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

	def get_install_requirements(self):
		# FIXME: extract this from the wheel
		#
		# pi = getinfo_pkginfo(self.local_path)
		# loop through pi.requires_dist
		return []

	@staticmethod
	def parse_filename(filename):
		def split_suffix(name):
			# better safe than sorry
			name = os.path.basename(name)

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
			_name, _version, _type = PythonArtefact.parse_filename(filename)

			if name:
				assert(name == _name)
			name = _name
			if version:
				assert(version == _version)
			version = _version
			if type:
				assert(type == _type)
			type = _type

		build = PythonArtefact(name, version, type)
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

class PythonPackageInfo(brcoti_core.PackageInfo):
	def __init__(self, name):
		super(PythonPackageInfo, self).__init__(canonical_package_name(name))

class PythonDownloadFinder(brcoti_core.DownloadFinder):
	def __init__(self, req, verbose):
		super(PythonDownloadFinder, self).__init__(verbose)

		if type(req) != PythonBuildRequirement:
			req = PythonBuildRequirement.from_string(req)

		self.name = req.name
		self.allow_prereleases = False

		# This is not good enough. We should consider all information
		# provided in the requirement.
		self.request_specifier = req.cooked_requirement.specifier

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

		best_match.cache = self.cache
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

		ji = d['info']
		info.home_page = ji['home_page']
		info.author = ji['author']

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
					pkgInfo = PythonArtefact(name, ver, type = type)
				elif type.startswith('bdist'):
					pkgInfo = PythonArtefact(name, ver, type = type)
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
		super(SimplePackageIndex, self).__init__(url + "/simple")

		# The trailing / is actually important, because otherwise
		# urljoin(base_url, "../../packages/blah/fasel")
		# will not do the right thing
		self._pkg_url_template = "{index_url}/{pkg_name}/"

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
		if rel != "internal" and rel is not None:
			print("IGNORING anchor with rel=%s" % rel)
			return None

		href = anchor.attrib['href']
		href, hash = urldefrag(href)

		# FIXME: this only works on systems that use '/' as the path separator
		filename = os.path.basename(href)
		assert(filename == anchor.text)

		try:
			name, version, type = PythonArtefact.parse_filename(filename)
			# print("%s => (\"%s\", \"%s\", \"%s\")" % (filename, name, version, type))
		except ValueError:
			print("WARNING: Unable to parse filename \"%s\" in SimpleIndex response" % filename)
			return None

		if type == 'rpm' or type == 'exe':
			return None

		build = PythonArtefact(name, version, type)
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
	def __init__(self, url, user, password):
		self.url = url
		self.config_written = False

		assert(user)
		assert(password)

		self.user = user
		self.password = password

	def describe(self):
		return "Python repository \"%s\"" % self.url

	def upload(self, build):
		assert(build.local_path)

		print("Uploading %s to %s repository" % (build.local_path, self.url))
		cmd = "twine upload --verbose "
		cmd += " --disable-progress-bar"
		cmd += " --repository-url %s" % (self.url)
		cmd += " --username %s" % (self.user)
		cmd += " --password %s" % (self.password)
		cmd += " " + build.local_path

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

		return brcoti_core.ArtefactComparison(other.path, added_set, removed_set, changed_set)

class PythonBuildStrategy(brcoti_core.BuildStrategy):
        pass

class BuildStrategy_Wheel(PythonBuildStrategy):
	_type = "wheel"

	def __init__(self, engine_config, *args):
		self.pip_command = engine_config.get_value("pip")
		if self.pip_command is None:
			self.pip_command = "pip"

	def describe(self):
		return self._type

	def next_command(self, build_directory):
		cmd = self.pip_command
		cmd += " wheel --wheel-dir dist ."
		cmd += " --log pip.log"
		cmd += " --no-deps"

		# KLUDGE ALERT
		# If translate_url() was used to map https://localhost to a hostname
		# that's working inside the container, we need to let pip know that
		# it should trust this hostname
		for hostname in build_directory.compute.trusted_hosts():
			cmd += " --trusted-host " + hostname

		yield cmd

class PythonBuildDirectory(brcoti_core.BuildDirectory):
	def __init__(self, compute, engine):
		super(PythonBuildDirectory, self).__init__(compute, compute.default_build_dir())

		self.build_info = brcoti_core.BuildInfo(engine.name)

	# Most of the unpacking happens in the BuildDirectory base class.
	# The only python specific piece is guessing which directory an archive is extracted to
	def archive_get_unpack_directory(self, sdist):
		name, version, type = PythonArtefact.parse_filename(sdist.filename)
		return name + "-" + version

	def infer_build_dependencies(self):
		return []

	def collect_build_results(self):
		# glob_files returns a list of ComputeResource* objects
		wheels = self.directory.glob_files(os.path.join("dist", "*.whl"))

		print("Successfully built %s: %s" % (sdist.id(), ", ".join([w.basename() for w in wheels])))
		for w in wheels:
			w = w.hostpath()

			# FIXME: use of hostpath is not pretty here. We should
			# save this to a host side directory right away
			build = PythonArtefact.from_local_file(w)

			for algo in PythonEngine.REQUIRED_HASHES:
				build.update_hash(algo)

			self.build_info.add_artefact(build)

		return self.build_info.artefacts

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
	#
	# This could be simpler. Current pip versions log lines like these:
	#   1 location(s) to search for versions of poetry-core:
	#   ...
	#   Using version 1.0.0 (newest of versions: 1.0.0)
	#   Collecting poetry-core>=1.0.0
	#   ...
	#
	def guess_build_dependencies(self):
		from packaging.requirements import Requirement
		import re

		logfile = self.directory.lookup("pip.log")
		if logfile is None:
			print("No pip.log found... expect problems")
			return

		print("Parsing pip.log")
		req = None

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
					req.cooked_requirement = r
					req.req_string = str(r)

					url, frag = urldefrag(url)
					if frag:
						algo, md = frag.split('=')
						req.add_hash(algo, md)

					req.filename = os.path.basename(urlparse(url).path)

					(name, version, type) = PythonArtefact.parse_filename(req.filename)
					artefact = PythonArtefact(name, version, type)
					artefact.filename = os.path.basename(req.filename)
					artefact.url = url

					req.resolution = artefact
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

				req = PythonBuildRequirement(name)
				self.build_info.add_requirement(req)
				if not self.quiet:
					print("Found requirement %s" % req.name)

		for req in self.build_info.requires:
			if not req.req_string:
				raise ValueError("pip log parser failed - unable to determine req string for build requirement %s" % req.name)

	def prepare_results(self, build_state):
		# Always upload the source tarball with the build artefacts
		if self.sdist not in self.build_info.artefacts:
			self.build_info.add_artefact(self.sdist)

		super(PythonBuildDirectory, self).prepare_results(build_state)

		self.maybe_save_file(build_state, "pip.log")

		for artefact in self.build_info.artefacts:
			if artefact.is_source:
				continue

			name = "%s-METADATA.txt" % artefact.id()
			pi = getinfo_pkginfo(artefact.local_path)
			build_state.write_file(name,
				pkginfo_as_metadata(pi),
				"%s metadata" % artefact.id())

	def maybe_save_file(self, build_state, name):
		fh = self.directory.lookup(name)
		if fh is None:
			print("Not saving %s/%s (does not exist)" % (self.directory, name))
			return None

		return build_state.save_file(fh)

	def write_file(self, build_state, name, write_func):
		buffer = io.StringIO()
		write_func(buffer)
		return build_state.write_file(name, buffer.getvalue())

# Publish a collection of python binary artefacts to a http tree (using a simple index).
# This is not very efficient, as we rebuild the entire tree whenever we do this.
# At least for the binary files themselves, it's probably better to just touch up an
# existing tree.
class PythonPublisher(brcoti_core.Publisher):
	def __init__(self, repoconfig):
		super(PythonPublisher, self).__init__("python", repoconfig)

	def prepare(self):
		self.prepare_repo_dir()

		self.index_dir = self.prepare_repo_subdir("simple")
		self.packages_dir = self.prepare_repo_subdir("packages")

		self.packages = {}

	def is_artefact(self, path):
		return path.endswith(".whl")

	def publish_artefact(self, path):
		# FIXME: this is not good enough; we will also need requires-python info
		(name, version, type) = PythonArtefact.parse_filename(os.path.basename(path))
		build = PythonArtefact(name, version, type)
		build.filename = os.path.basename(path)
		build.local_path = path

		build.update_hash("sha256")

		pi = self.packages.get(name)
		if pi is None:
			pi = PythonPackageInfo(name)
			self.packages[name] = pi

		release = PythonReleaseInfo(name, version)
		release.add_build(build)

		pi.add_release(release)

	def finish(self):
		print("Writing index files")
		for pi in self.packages.values():
			pkg_index_path = os.path.join(self.index_dir, pi.name)
			if not os.path.isdir(pkg_index_path):
				os.makedirs(pkg_index_path, 0o755)

			f = self.simple_index_open(pi.name)
			for release in sorted(pi.releases, key = lambda r : r.parsed_version):
				for build in release.builds:
					if build.type == 'bdist_wheel':
						self.simple_index_write_build(f, build)

			self.simple_index_write_trailer(f)

		print("Copying wheels")
		for pi in self.packages.values():
			for release in pi.releases:
				for build in release.builds:
					if build.type != 'bdist_wheel':
						continue

					location = self.package_location(build)
					location = os.path.join(self.packages_dir, location)

					dir = os.path.dirname(location)
					if not os.path.exists(dir):
						os.makedirs(dir, mode = 0o755)
					shutil.copy(build.local_path, location)

		self.simple_index_top_write([pi.name for pi in self.packages.values()])

	pkg_index_header = (
		'<!DOCTYPE html>',
		'<html>',
		'  <head>',
		'    <title>Links for %PKG</title>',
		'  </head>',
		'  <body>',
		'    <h1>Links for %PKG</h1>',
	)
	pkg_index_trailer = (
		'  </body>',
		'</html>',
	)
	def simple_index_open(self, pkg_name):
		pkg_index_path = os.path.join(self.index_dir, pkg_name)
		if not os.path.isdir(pkg_index_path):
			os.makedirs(pkg_index_path, 0o755)

		f = open(os.path.join(pkg_index_path, "index.html"), "w")
		for l in self.pkg_index_header:
			l = l.replace("%PKG", pkg_name)
			print(l, file = f)

		return f

	def simple_index_write_build(self, f, build, algo = "sha256"):
		# If the build requires specific python versions, we'll have to add something like
		# data-requires-python="&gt;=3.4" or worse data-requires-python="&gt;=2.7, !=3.0, !=3.1, !=3.2, != 3.3"

		location = self.package_location(build)

		line = "    <a href=\"../../packages/%s#%s=%s\">%s</a><br/>" % (location, algo, build.get_hash(algo), build.filename)
		print(line, file = f)

	def simple_index_write_trailer(self, f):
		for l in self.pkg_index_trailer:
			print(l, file = f)

	def package_location(self, build):
		# pythonhosted.org uses a two-level hierarchy based on the file's hash, but
		# for the time being, we don't go there. Not enough meat yet.
		return build.filename

	top_index_header = (
		'<html>',
		'  <head>',
		'    <title>Simple index</title>',
		'  </head>',
		'  <body>',
	)
	top_index_trailer = (
		'  </body>',
		'</html>',
	)

	def simple_index_top_write(self, names):
		path = os.path.join(self.index_dir, "index.html")
		with open(path, "w") as f:
			for l in self.top_index_header:
				print(l, file = f)

			for name in names:
				line = "    <a href=\"/simple/%PKG/\">%PKG</a>".replace("%PKG", name)
				print(line, file = f)

			for l in self.top_index_trailer:
				print(l, file = f)

class PythonEngine(brcoti_core.Engine):
	type = 'python'

	REQUIRED_HASHES = ('md5', 'sha256')

	def __init__(self, config, engine_config):
		super(PythonEngine, self).__init__(config, engine_config)

	def create_index_from_repo(self, repo_config):
		repotype = repo_config.repotype or "simple"
		if repotype == 'json': 
			return JSONPackageIndex(repo_config.url)
		elif repotype == 'simple':
			return SimplePackageIndex(repo_config.url)
		else:
			raise ValueError("Don't know how to create a %s index for url %s" % (repo_config.repotype, repo_config.url))

	def create_uploader_from_repo(self, repo_config):
		return PythonUploader(repo_config.url, user = repo_config.user, password = repo_config.password)

	def create_publisher_from_repo(self, repo_config):
		return PythonPublisher(repo_config)

	def create_binary_download_finder(self, req, verbose = True):
		return PythonBinaryDownloadFinder(req, verbose)

	def create_source_download_finder(self, req, verbose = True):
		return PythonSourceDownloadFinder(req, verbose)

	# Used by build-requires parsing
	def create_empty_requirement(self, name):
		return PythonBuildRequirement(name)

	def parse_build_requirement(self, req_string):
		return PythonBuildRequirement.from_string(req_string)

	def prepare_environment(self, compute_backend, build_info):
		compute = super(PythonEngine, self).prepare_environment(compute_backend, build_info)
		# FIXME: this should happen in the pip build stategy
		compute.putenv("PIP_INDEX_URL", compute.translate_url(self.default_index.url))
		return compute

	def create_artefact_from_local_file(self, path):
		return PythonArtefact.from_local_file(path)

	def create_artefact_from_NVT(self, name, version, type):
		if type == 'source':
			type = 'sdist'
		return PythonArtefact(name, version, type)

	def infer_build_requirements(self, sdist):
		# We don't do that
		return []

	def install_requirement(self, compute, req):
		raise NotImplementedError("%s: installation of extra requirements currently not implemented" % self.type)

	def create_build_strategy_default(self):
		return BuildStrategy_Wheel(self.engine_config)

	def create_build_strategy(self, name, *args):
		if name == 'default' or name == 'auto' or name == 'wheel':
                        return BuildStrategy_Wheel(self.engine_config)

		super(PythonEngine, self).create_build_strategy(name, *args)

	def create_build_directory(self, compute):
		return PythonBuildDirectory(compute, self)

	def resolve_build_requirement(self, req):
		finder = PythonBinaryDownloadFinder(req)
		return finder.get_best_match(self.default_index)

def engine_factory(config, engine_config):
	return PythonEngine(config, engine_config)
