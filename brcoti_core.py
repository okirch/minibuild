#!/usr/bin/python3
#
# This is a simplistic build script for building artefacts of various
# programming languages natively (eg using pip, npm etc) and upload the
# resulting artefacts to a local repo.
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
import glob
import shutil
import re
import tempfile
import subprocess

def __pre_command():
	# Avoid messing up the order of our output and the output of subprocesses when
	# stdout is redirected
	sys.stdout.flush()
	sys.stderr.flush()

def run_command(cmd, ignore_exitcode = False):
	print("Running %s" % cmd)

	__pre_command()
	completed = subprocess.run(cmd, shell = True, stdout = sys.stdout, stderr = sys.stderr, stdin = None)

	rv = completed.returncode
	if rv != 0 and not ignore_exitcode:
		raise ValueError("Command `%s' returned non-zero exit status" % cmd)

def popen(cmd, mode = 'r'):
	print("Running %s" % cmd)

	__pre_command()
	return os.popen(cmd, mode)

class Object(object):
	def mni(self):
		import sys
		import traceback
		import threading

		my_thread = threading.current_thread()
		for thread, frame in sys._current_frames().items():
			if thread != my_thread.ident:
				continue

			if frame.f_code.co_name != 'mni':
				break

			frame = frame.f_back
			raise NotImplementedError("%s.%s(): method not implemented" % (self.__class__.__name__, frame.f_code.co_name))

		# we were trying to be too clever; or something changed in the way python handles stack frames.
		# Fall back to a more bland error message
		raise NotImplementedError("%s: method not implemented" % (self.__class__.__name__))

class ArtefactAttrs(Object):
	engine = "UNKNOWN"

	def __init__(self, name, version = None):
		self.name = name
		self.version = version
		self.hash = {}

	def __repr__(self):
		return self.id()

	def id(self):
		if not self.version:
			return self.name
		return "%s-%s" % (self.name, self.version)

	def get_hash(self, algo):
		return self.hash.get(algo)

	def add_hash(self, algo, md):
		self.hash[algo] = md

	# Subclasses that implement different fingerprinting methods
	# should override this
	# (Or we should remove it here and create a mixin class instead)
	def update_hash(self, algo):
		import hashlib

		m = hashlib.new(algo)
		with open(self.local_path, "rb") as f:
			m.update(f.read())

		self.add_hash(algo, m.hexdigest())

class BuildRequirement(ArtefactAttrs):
	def __init__(self, name, req_string = None, cooked_requirement = None):
		super(BuildRequirement, self).__init__(name)

		if req_string and not cooked_requirement:
			self.parse_requirement(req_string)
		else:
			self.req_string = req_string
			self.cooked_requirement = cooked_requirement

		self.resolution = None
		self.origin = None

	def parse_requirement(self, req_string):
		self.mni()

	def __repr__(self):
		if self.cooked_requirement:
			return repr(self.cooked_requirement)
		if self.req_string:
			return self.req_string
		return self.name

class Artefact(ArtefactAttrs):
	def __init__(self, name, version = None):
		super(Artefact, self).__init__(name, version)

		self.url = None
		self.local_path = None
		self.git_repo_url = None
		self.git_repo_tag = None

		self.cache = None

	def __repr__(self):
		return "%s(%s)" % (self.__class__.__name__, self.id())

	def git_url(self):
		return self.git_repo_url

	def git_tag(self):
		return self.git_repo_tag

	@property
	def is_source(self):
		self.mni()

	# By default, an artefact implementation does not provide information
	# on install requirements
	def get_install_requirements(self):
                return []

class ArtefactComparison(Object):
	def __init__(self, name, added = set(), removed = set(), changed = set()):
		self.name = name
		self.added = added
		self.removed = removed
		self.changed = changed

		self.differs = dict()

	def __bool__(self):
		return not(self.added or self.removed or self.changed)

	def print(self):
		def print_delta(how, name_set):
			if not name_set:
				print("  none %s" % how)
			else:
				print("  %d file(s) %s:" % (len(name_set), how))
				for name in name_set:
					print("    %s" % name)

		print("%s comparison results:" % os.path.basename(self.name))
		print_delta("added", self.added)
		print_delta("removed", self.removed)
		print_delta("changed", self.changed)

	def show_diff(self):
		for name in self.changed:
			d = self.get_differ(name)
			if not d:
				print("%s: no diff available" % name)
				continue

			d.show()

	def get_differ(self, name):
		return self.differs.get(name)

	def add_differ(self, differ):
		self.differs[differ.name] = differ

	def add_raw_data_differ(self, name, old_data, new_data):
		self.add_differ(self.RawDataDiffer(name, old_data, new_data))

	class RawDataDiffer:
		def __init__(self, name, old, new):
			self.name = name
			self.old_data = old
			self.new_data = new

		def show(self):
			import tempfile

			self.tmpdir = tempfile.TemporaryDirectory(prefix = "brcoti-")

			old_path = self.write_data("old", self.old_data)
			new_path = self.write_data("new", self.new_data)

			run_command("diff -wau %s %s" % (old_path, new_path), ignore_exitcode = True)

			self.tmpdir = None

		def write_data(self, tag, data):
			path = os.path.join(self.tmpdir.name, tag, self.name)
			dirname = os.path.dirname(path)
			if not os.path.isdir(dirname):
				os.makedirs(dirname)
			with open(path, "wb") as f:
				f.write(data)

			return path

class PackageReleaseInfo(Object):
	def __init__(self, name, version):
		self.name = name
		self.version = version

		self.builds = []

	def id(self):
		self.mni()

	def more_recent_than(self, other):
		self.mni()

	def add_build(self, build):
		self.builds.append(build)

class PackageInfo(Object):
	def __init__(self, name):
		self.name = name
		self.releases = []

	def add_release(self, release):
		self.releases.append(release)

	def versions(self):
		return [r.version for r in self.releases]

class EngineSpecificRequirementSet(Object):
	def __init__(self, engine_name):
		self.engine_name = engine_name
		self.req_dict = dict()

	@property
	def requirements(self):
		self.mni()

	def add(self, req):
		# print("EngineSpecificRequirementSet.add(%s)" % req)

		existing_req = self.req_dict.get(req.name)
		if existing_req is None:
			# Easy case
			self.req_dict[req.name] = req
			return True

		if existing_req == req:
			return False

		# Merge the two requirements into one, if possible
		self.req_dict[req.name] = existing_req.merge(req)
		return True

	def all(self):
		return self.req_dict.values()

	def __iter__(self):
		return sorted(self.req_dict.values(), key = lambda r: r.name)

class RequirementSet(Object):
	def __init__(self):
		self.engine_dict = dict()

	def add(self, req):
		engine_name = req.engine
		engine_set = self.engine_dict.get(req.engine)
		if engine_set is None:
			engine_set = EngineSpecificRequirementSet(engine_name)
			self.engine_dict[req.engine] = engine_set

		engine_set.add(req)

	def add_list(self, req_list):
		for req in req_list:
			self.add(req)

	def all(self):
		result = []
		for engine_set in self.engine_dict.values():
			result += engine_set.all()
		return result


	def show(self, msg):
		if msg:
			print(msg)
		for (engine_name, engine_set) in self.engine_dict.items():
			req_list = engine_set.all()
			if not req_list:
				continue
			print("  %s requirements:" % engine_name)
			for req in req_list:
				if req.origin:
					print("   %s (via %s)" % (req.format(), req.origin))
				else:
					print("   %s" % req.format())

	def __iter__(self):
		return self.engine_dict.items()

class DownloadFinder(Object):
	def __init__(self, verbose):
		self.verbose = verbose

	def get_best_match(self, index):
		self.mni()

class PackageIndex(Object):
	def get_package_info(self, name):
		self.mni()

class HTTPPackageIndex(PackageIndex):
	def __init__(self, url):
		self.url = url
		self._pkg_url_template = None

		self.cache = DownloadCache()

	def zap_cache(self):
		self.cache.zap()

	def get_package_info(self, name):
		import urllib.request
		from urllib.error import HTTPError

		url = self._pkg_url_template.format(index_url = self.url, pkg_name = name)

		try:
			resp = urllib.request.urlopen(url)
			status = resp.status
			reason = resp.reason
		except HTTPError as e:
			print(e.strerror)
			status = e.code
			reason = e.reason

		if status != 200:
			raise ValueError("Unable to get package info for %s from %s: HTTP response %s (%s)" % (
					name, url, status, reason))

		return self.process_package_info(name, resp)

	# returns a PackageInfo object
	def process_package_info(self, name, http_resp):
		self.mni()

# For now, this is a very trivial downloader.
# This could be something much more complex that uses caches, OBS, yadda yadda
class Downloader(object):
	def __init__(self):
		pass

	def download_to(self, build, destdir, quiet = False):
		filename = os.path.join(destdir, build.filename)
		cached_filename = self._download(build, filename, quiet)
		if cached_filename != filename:
			shutil.copy(cached_filename, filename)
		return filename

	def download(self, build, quiet = False):
		filename = build.filename

		if False:
			# This is a bad idea. Among other things, this won't
			# set build.local_path
			if os.path.isfile(filename):
				return filename

		return self._download(build, filename, quiet)

	def _download(self, build, path, quiet = False):
		import urllib.request

		if build.cache and not build.local_path:
			build.local_path = build.cache.get(build.filename)

		if build.local_path:
			return build.local_path

		assert(build.url)
		assert(build.filename)

		url = build.url
		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to download %s from %s (HTTP status %s %s)" % (
					build.filename, url, resp.status, resp.reason))

		filename = build.filename
		if path:
			filename = path

		if build.cache:
			filename = build.cache.create(build.filename)

		with open(filename, "wb") as f:
			f.write(resp.read())

		if not quiet:
			print("Downloaded %s from %s" % (filename, url))

		build.local_path = filename
		return filename

class DownloadCache(object):
	def __init__(self, path = None):
		self.tempdir = None

		if path is None:
			self.tempdir = tempfile.TemporaryDirectory(prefix = "brcoti-cache-")
			path = self.tempdir.name

		self.path = path

	def zap(self):
		# for now
		pass

	def get(self, filename):
		filename = os.path.basename(filename)
		assert(filename)

		path = os.path.join(self.path, filename)
		if os.path.isfile(path):
			return path

		return None

	def create(self, filename):
		filename = os.path.basename(filename)
		assert(filename)

		return os.path.join(self.path, filename)

# For now, a very trivial uploader.
class Uploader(Object):
	def __init__(self):
		pass

	def describe(self):
		self.mni()

	def upload(self, build):
		self.mni()

class BuildInfo(Object):
	def __init__(self):
		self.build_script = None
		self.build_strategy = None
		self.requires = []
		self.artefacts = []
		self.sources = []
		self.source_urls = []
		self.no_default_patches = False
		self._patches = []
		self.used = []
		self.tag_pattern = None

		self.requires_set = RequirementSet()

	@property
	def source(self):
		if not self.sources:
			return None
		return self.sources[0]

	def add_requirement(self, req):
		self.requires.append(req)

		self.requires_set.add(req)

	def add_artefact(self, build):
		self.artefacts.append(build)

	def add_used(self, build):
		self.used.append(build)

	def write(self, f):
		self.write_build_requires(f)
		self.write_artefacts(f, "built", self.artefacts)
		self.write_artefacts(f, "used", self.used)
		self.write_sources(f)

		if self.build_strategy:
			print("build-strategy %s" % self.build_strategy.describe(), file = f)
		elif self.build_script:
			print("build %s" % self.build_script, file = f)

		for patch in self._patches:
			patch = os.path.basename(patch)
			print("patch %s" % patch, file = f)

	#
	# Write out the build-requires information
	#
	def write_build_requires(self, f):
		seen = set()
		for req in self.requires:
			req_string = "%s %s" % (req.engine, req.format())
			if req_string in seen:
				continue
			seen.add(req_string)

			print("require %s" % req_string, file = f)
			self.write_hashes(req, f)

			artefact = req.resolution
			if artefact:
				if artefact.filename:
					print("  filename %s" % artefact.filename, file = f)
				if artefact.url:
					print("  url %s" % artefact.url, file = f)

	def parse_requires(self, line):
		(name, rest) = line.split(maxsplit = 1)

		engine = Engine.factory(name)
		obj = engine.parse_build_requirement(rest.strip())
		obj.origin = 'spec'
		self.add_requirement(obj)
		return obj

	def write_artefacts(self, f, keyword, artefact_list):
		for build in artefact_list:
			print("%s %s %s %s %s" % (keyword, build.engine, build.name, build.version, build.type), file = f)
			print("  filename %s" % build.filename, file = f)

			self.write_hashes(build, f)

	def parse_artefact(self, line):
		name, *args = line.split()

		engine = Engine.factory(name)
		obj = engine.create_artefact_from_NVT(*args)
		self.add_artefact(obj)
		return obj

	def parse_used(self, line):
		name, *args = line.split()

		engine = Engine.factory(name)
		obj = engine.create_artefact_from_NVT(*args)
		self.add_used(obj)
		return obj

	def write_sources(self, f):
		# If all of our sources were constructed from git-repo urls
		# plus version/tag information, we don't write them out
		# explicitly.
		if self.explicit_git_urls() != self.implicit_git_urls():
			#print("explicit urls:", self.explicit_git_urls())
			#print("implicit urls:", self.implicit_git_urls())
			for sdist in self.sources:
				if sdist.git_repo_url is None:
					print("source %s" % sdist.filename, file = f)
					self.write_hashes(sdist, f)
				else:
					url = self.format_url(sdist.git_url())
					print("source %s" % url, file = f)

		for url in self.source_urls:
			print("git-repo %s" % url, file = f)

	def explicit_git_urls(self):
		result = []
		for sdist in self.sources:
			url = sdist.git_url()
			if url is None:
				return None
			result.append(self.format_url(url, name = sdist.name))
		return result

	def parse_git_tag_pattern(self, line):
		self.tag_pattern = line.strip()
		assert("$VERSION" in self.tag_pattern)

	def parse_git_tag(self, line):
		tag = line.strip()
		if "=" in tag:
			(repo_name, tag) = tag.split("=", 1)
			self.tag_for[repo_name] = tag
		else:
			self.tag = line.strip()

	def parse_git_repo(self, line):
		self.source_urls.append(line.strip())

	def parse_exclude_git_repo(self, line):
		if self.exclude_git_repos is None:
			self.exclude_git_repos = set()
		self.exclude_git_repos.add(line.strip())

	def parse_include_git_repo(self, line):
		if self.include_git_repos is None:
			self.include_git_repos = set()
		self.include_git_repos.add(line.strip())

	def parse_source(self, line):
		return self.add_source(line.strip())

	def add_source(self, arg):
		build_engine = self.context_engine()

		if isinstance(arg, Artefact):
			sdist = arg
		elif arg.startswith("git:") or arg.startswith("http:") or arg.startswith("https:"):
			sdist = build_engine.create_artefact_from_url(arg,
					package_name = self.context_name(),
					version = self.version)
		else:
			filename = os.path.join(os.path.dirname(path), arg)
			filename = os.path.realpath(filename)
			sdist = build_engine.create_artefact_from_local_file(filename)

		self.sources.append(sdist)
		return sdist

	def parse_patch(self, path, line):
		arg = line.strip()
		filename = os.path.join(os.path.dirname(path), arg)
		filename = os.path.realpath(filename)

		if not os.path.exists(filename):
			raise ValueError("patch %s does not exist" % arg)
		self._patches.append(filename)

	def write_hashes(self, attrs, f):
		if attrs.hash:
			for (algo, md) in attrs.hash.items():
				print("  hash %s %s" % (algo, md), file = f)

	def parse_build_script(self, path, line):
		build_engine = self.context_engine()

		arg = line.strip()
		filename = os.path.join(os.path.dirname(path), arg)
		filename = os.path.realpath(filename)

		if not os.access(filename, os.X_OK):
			raise ValueError("build script %s must be executable" % arg)

		self.build_script = arg
		self.build_strategy = build_engine.create_build_strategy_from_script(filename)

	def parse_build_strategy(self, path, line):
		build_engine = self.context_engine()

		self.build_strategy = BuildStrategy.parse(build_engine, line.strip())

class VersionSpec(BuildInfo):
	def __init__(self, build_spec, version):
		super(VersionSpec, self).__init__()

		self.parent = build_spec
		self.engine = build_spec.engine
		self.package_name = build_spec.package_name
		self.version = version
		self.tag = None

		self.exclude_git_repos = set()
		self.include_git_repos = None
		self.tag_for = {}

	def id(self):
		return "%s-%s" % (self.package_name, self.version)

	@property
	def dependencies(self):
		defaults = []
		if self.parent and self.parent.defaults:
			defaults = self.parent.defaults.requires

		return defaults + self.requires

	@property
	def patches(self):
		if self.no_default_patches:
			return self._patches

		defaults = []
		if self.parent and self.parent.defaults:
			defaults = self.parent.defaults._patches

		return defaults + self._patches

	def write(self, f):
		print("", file = f)
		if self.version:
			print("version %s" % self.version, file = f)
		else:
			print("# defaults", file = f)

		if self.tag_pattern:
			print("git-tag-pattern %s" % self.tag_pattern, file = f)

		if self.tag:
			print("git-tag %s" % self.tag, file = f)

		for (name, tag) in self.tag_for:
			print("git-tag %s=%s" % (name, tag))

		for repo in self.exclude_git_repos:
			print("exclude-git-repo %s" % rep)

		if self.include_git_repos is not None:
			for repo in self.include_git_repos:
				print("include-git-repo %s" % rep)

		if self.no_default_patches:
			print("no-default-patches", file = f)

		super(VersionSpec, self).write(f)

	def context_name(self):
		return self.parent.context_name()

	def context_engine(self):
		return self.parent.context_engine()

	def implicit_git_urls(self):
		result = []

		source_urls = self.source_urls
		if not source_urls:
			source_urls = self.parent.defaults.source_urls

		for i in range(len(source_urls)):
			repo_url = source_urls[i]

			if i == 0:
				name = self.package_name
			else:
				repo_url = repo_url.rstrip('/')
				name = repo_url.split('/')[-1]

				if name in self.exclude_git_repos:
					continue

				if self.include_git_repos is not None and \
				   name not in self.include_git_repos:
					continue

			url = self.format_url(repo_url, name)

			if url:
				result.append(url)
		return result

	def format_url(self, repo_url, name = None):
		attrs = []
		if name:
			attrs.append("name=%s" % name)
		attrs.append("version=%s" % self.version)

		tag = self.tag_for.get(name)
		if tag is None:
			tag = self.tag
		if tag is None and self.parent.defaults.tag_pattern:
			tag = self.parent.defaults.tag_pattern.replace("$VERSION", self.version)
		if tag:
			attrs.append("tag=%s" % tag)

		return "%s?%s" % (repo_url, "&".join(attrs))


class DefaultSpec(VersionSpec):
	def __init__(self, build_spec):
		super(DefaultSpec, self).__init__(build_spec, None)

	def add_source(self, url_or_path):
		self.source_urls.append(url_or_path)

class BuildSpec(Object):
	def __init__(self, engine):
		super(BuildSpec, self).__init__()

		self.engine = engine

		self.package_name = None

		self.defaults = DefaultSpec(self)
		self.versions = []

		self.build_engine = None

	def save(self, path):
		with open(path, "w") as f:
			print("engine %s" % self.engine, file = f)

			if self.package_name:
				print("package %s" % self.package_name, file = f)

			# self.write(f)
			if self.defaults:
				self.defaults.write(f)
			for v in self.versions:
				v.write(f)

	def validate(self, path):
		if self.engine is None:
			raise ValueError("%s: does not specify an engine" % path)

		if not self.package_name:
			raise ValueError("%s: does not specify a package name" % path)

		if not self.versions:
			raise ValueError("%s: does not specify any versions" % path)

		for v in self.versions:
			if v.sources:
				continue

			for url in v.implicit_git_urls():
				v.add_source(url)

			if not v.sources:
				raise ValueError("%s: version %s does not specify any sources" % (path, v.version))

	#
	# Parse the build-requires file
	#
	@staticmethod
	def from_file(path, default_engine = None):
		print("Loading build info from %s" % path)
		result = BuildSpec(None)

		engine = default_engine
		result.build_engine = default_engine

		version = result.defaults
		with open(path, 'r') as f:
			req = None
			for l in f.readlines():
				if l.startswith('#'):
					continue
				l = l.rstrip()
				if not l:
					continue

				if not l.startswith(' '):
					# reset the engine
					engine = None
					obj = None

					(kwd, *rest_of_line) = l.split(maxsplit = 1)
					if rest_of_line:
						l = rest_of_line[0]
					else:
						l = ""

					if kwd == 'package':
						if result.package_name:
							raise ValueError("%s: duplicate package specification" % path)
						result.package_name = l.strip()
					elif kwd == 'engine':
						result.parse_engine(path, l, default_engine)
					elif kwd == 'version':
						version = result.add_version(l.strip())
					elif kwd in ('require', 'artefact', 'built', 'used'):
						if kwd == 'require':
							obj = version.parse_requires(l)
						elif kwd == 'artefact' or kwd == 'built':
							obj = version.parse_artefact(l)
						elif kwd == 'used':
							obj = version.parse_used(l)
					elif kwd == 'git-repo':
						version.parse_git_repo(l)
					elif kwd == 'exclude-git-repo':
						version.parse_exclude_git_repo(l)
					elif kwd == 'include-git-repo':
						version.parse_include_git_repo(l)
					elif kwd == 'git-tag-pattern':
						version.parse_git_tag_pattern(l)
					elif kwd == 'git-tag':
						version.parse_git_tag(l)
					elif kwd == 'source':
						version.parse_source(l)
					elif kwd == 'build':
						version.parse_build_script(path, l)
					elif kwd == 'build-strategy':
						version.parse_build_strategy(path, l)
					elif kwd == 'patch':
						version.parse_patch(path, l)
					elif kwd == 'no-default-patches':
						version.no_default_patches = True
					else:
						raise ValueError("%s: unexpected keyword \"%s\"" % (path, kwd))
				else:
					words = l.split()
					kwd = words.pop(0)

					if not words:
						raise ValueError("%s: unparseable line <%s>" % (path, l))

					if kwd == 'hash':
						obj.add_hash(words[0], words[1])
					elif kwd == 'filename':
						# This is not quite right for Requirements objects
						obj.filename = words[0]
					elif kwd == 'url':
						# This is not quite right for Requirements objects
						obj.url = words[0]
					else:
						raise ValueError("%s: unparseable line <%s>" % (path, l))

		# Old-style build-spec files did not have separate "version" sections, but just a single
		# one.
		if not result.versions:
			v = result.defaults
			if len(v.sources) == 0 and len(v.source_urls) == 1:
				result.defaults = DefaultSpec(result)

				url_or_path = v.source_urls[0]
				try:
					sdist = result.build_engine.create_artefact_from_url(url_or_path)
				except:
					sdist = None

				if sdist:
					result.package_name = sdist.name
					v.version = sdist.version
					v.sources = [sdist]
					v.source_urls = []

					if sdist.git_repo_url:
						result.defaults.add_source(sdist.git_repo_url)
						v.tag = sdist.git_repo_tag

				result.versions.append(v)


		result.validate(path)
		return result

	def parse_engine(self, path, line, default_engine):
		if self.engine:
			raise ValueError("%s: duplicate engine specification" % path)
		self.engine = line.strip()
		if default_engine and self.engine != default_engine.name:
			raise ValueError("Beware, %s specifies engine \"%s\" which conflicts with engine %s" % (
				path, self.engine, default_engine.name))

		self.build_engine = Engine.factory(self.engine)
		return self.build_engine

	def add_version(self, version_str):
		version = VersionSpec(self, version_str)
		self.versions.append(version)

		return version

	def context_name(self):
		return self.package_name

	def context_engine(self):
		return self.build_engine

class Source(Object):
	def __init__(self):
		self.path = None

	def merge_info_from_build(self, build_info):
		self.spec.requires += build_info.requires

		if len(build_info.sources) >= 1:
			sdist = build_info.sources[0]

			if sdist.git_url():
				self.spec.tag = sdist.git_tag()
				self.spec.source_urls.append(sdist.git_url())

	def add_requires(self, req_list):
		self.spec.requires += req_list

	def save(self, path = None, spec_name = "build-spec"):
		if path is None:
			path = self.path
			if path is None:
				raise ValueError("Unable to save source; path is not set");
		else:
			if os.path.exists(path):
				raise ValueError("Refusing to save source to %s: file or directory exists" % path)

			os.makedirs(path, mode = 0o755)

		for sdist in self.spec.sources:
			# FIXME: only copy those that were added/modified
			if sdist.local_path is not None:
				shutil.copy(sdist.local_path, path)

		spec_path = os.path.join(path, spec_name)
		self.spec_file.save(spec_path)

class SourceFile(Source):
	def __init__(self, sdist, engine):
		self.spec_file = BuildSpec(engine.name)
		self.spec_file.package_name = sdist.name
		self.spec = self.spec_file.add_version(sdist.version)
		self.spec.add_source(sdist)

	def id(self):
		return self.spec.sources[0].id()

class SourceDirectory(Source):
	def __init__(self, path, config):
		self.path = path
		self.spec_file = None
		self.spec = None

		if not os.path.isdir(path):
			raise ValueError("%s: not a directory" % path)

		spec_path = os.path.join(path, "build-spec")
		if not os.path.exists(spec_path):
			# fall back to older name
			spec_path = os.path.join(path, "build-info")
			if not os.path.exists(spec_path):
				raise ValueError("%s: no build-spec file, and no build-info fallback" % path)

			print("Found build-info file; please rename to build-spec at your convenience")

		self.spec_file = BuildSpec.from_file(spec_path)

		for v in self.spec_file.versions:
			if v.source is not None:
				self.spec = v
				break

	def select_version(self, version):
		for v in self.spec_file.versions:
			if v.version == version:
				self.spec = v
				return True

		return False

	def from_closest_version(self, version):
		if not self.spec_file.versions:
			return False

		closest = self.spec_file.versions[-1]

		new_ver = self.spec_file.add_version(version)
		new_ver.build_strategy = closest.build_strategy

		for url in new_ver.implicit_git_urls():
			# sdist = self.spec_file.build_engine.create_artefact_from_url(url)
			new_ver.add_source(url)

		if not new_ver.source:
			raise ValueError("Don't know how to determine source for %s" % new_ver.id())

		# FIXME copy other settings?

		self.spec = new_ver
		return True

	def id(self):
		assert(self.spec)
		return self.spec.id()

class BuildStrategy(Object):
	# Derived classes that have static build dependencies should define a
	# class attribute _requires containing strings
	_requires = []

	def __init__(self):
		pass

	def describe(self):
		self.mni()

	def next_command(self):
		self.mni()

	def build_dependencies(self, build_directory):
		return self._build_dependencies(build_directory)

	def _build_dependencies(self, build_directory, nested_strategy = None, engine_name = None):
		result = []
		for name in self._requires:
			if build_directory.has_build_dependency(name, engine_name):
				print("Build strategy asks for %s, but we already have a requirement for this." % name)
			else:
				result.append(name)
		if nested_strategy:
			result += nested_strategy.build_dependencies(build_directory)
		return result

	def build_used(self, build_directory):
		return []

	def resolve_source(self, source):
		return

	def implicit_build_dependencies(self, build_directory):
		return []

	@staticmethod
	def parse(engine, arg):
		# print("BuildStrategy.parse(\"%s\")" % arg)
		values = BuildStrategy.parse_expression_list(engine, arg)
		if values is None:
			raise ValueError("BuildStrategy.parse(%s) failed" % arg)

		assert(len(values) == 1)

		result = values[0]
		if not isinstance(result, BuildStrategy):
			result = engine.create_build_strategy(result)

		if arg.replace(' ', '') != result.describe().replace(' ', ''):
			raise ValueError("BuildStrategy.parse(\"%s\") failed: created \"%s\" instead" % (arg, result.describe()))

		return result

	@staticmethod
	def parse_expression_list(engine, arg, indent = 0, debug = False):
		ws = " " * indent

		if debug:
			print("%sparse_expression_list(\"%s\")" % (ws, arg))

		rest = arg.strip()
		result = []

		while rest:
			if debug:
				print("%s  Partial: <%s>" % (ws, rest))

			if rest.startswith("\""):
				m = re.search('"([^"]*)"(.*)', rest)
			else:
				m = re.search("([-A-Za-z_]*)(.*)", rest)
			if not m:
				return None

			id_or_string = m.group(1)
			rest = m.group(2).strip()

			if debug:
				print("%s  => %s | %s" % (ws, id_or_string, rest))

			if rest.startswith("("):
				m = re.search("\((.*)\)(.*)", rest)
				if not m:
					return None

				if debug:
					print("%s  Parsing argument list of call to %s()" % (ws, id_or_string))

				args = BuildStrategy.parse_expression_list(engine, m.group(1), indent + 2)
				if args is None:
					raise ValueError("BuildStrategy.parse(%s) failed" % m.group(1))

				if debug:
					print("%s  Creating build strategy %s with args %s" % (ws, id_or_string, args))

				strategy = engine.create_build_strategy(id_or_string, *args)
				if strategy is None:
					raise ValueError("Failed to create build strategy %s with args %s" % (id_or_string, args))

				if debug:
					print("%s  created %s" % (ws, strategy.describe()))

				result.append(strategy)
				rest = m.group(2).strip()
			else:
				result.append(id_or_string)

			if rest and not rest.startswith(","):
				return None

			rest = rest[1:].strip()

		if debug:
			print("%sReturning %s" % (ws, result))

		return result

class BuildStrategy_FromScript(BuildStrategy):
	_type = "script"

	def __init__(self, path):
		self.path = path
		self.full_path = None

	def describe(self):
		# For now, we assume that the script always lives inside the source directory
		return "%s(\"%s\")" % (self._type, os.path.basename(self.path))

	def resolve_source(self, source):
		if not isinstance(source, SourceDirectory):
			raise ValueError("build-strategy script: source is not a SourceDirectory");

		self.full_path = os.path.join(source.path, self.path)

	def next_command(self, build_directory):
		build_script = self.full_path
		if not build_script:
			raise ValueError("build-strategy script: no full path for script \"%s\" - did you forget to call resolve_source()?" % self.path);

		installed_path = build_directory.install_extra_file(build_script)

		yield installed_path

		# Record the fact that we used a build script (for now)
		# self.build_info.build_script = build_script

class BuildFailure(Exception):
	def __init__(self, msg, cmd):
		super(BuildFailure, self).__init__(msg)
		self.cmd = cmd

class BuildAborted(Exception):
	pass

class UnsatisfiedDependencies(Exception):
	def __init__(self, msg, req_list, remedy = None):
		super(UnsatisfiedDependencies, self).__init__(msg)
		self.dependencies = req_list
		self.remedy = remedy

	def __repr__(self):
		return "UnsatisfiedDepdencies(%s)" % self.format_dependencies()

	def format_dependencies(self):
		return ";".join([req.format() for req in self.dependencies])

class BuildDirectory(Object):
	def __init__(self, compute, engine):
		self.compute = compute
		self.engine = engine

		# This is where we record auto-detected build information
		self.built_spec = BuildSpec(engine.name)
		self.build_info = None

		build_base = compute.default_build_dir()
		self.build_base = self.compute.get_directory(build_base)
		assert(self.build_base)

		self.directory = None
		self.sdist = None
		self.quiet = False
		self.build_log = None

		self.http_proxy = None

		self.explicit_requirements_installed = []

	def cleanup(self):
		if self.directory:
			self.directory.rmtree()

	@property
	def location(self):
		return self.build_base.path

	def set_logging(self, quiet = None, build_log = None):
		if quiet is not None:
			self.quiet = quiet
		if build_log is not None:
			self.build_log = build_log

	def unpacked_dir(self):
		if not self.directory:
			return "<none>"

		return self.directory.path

	# This is called right after creating the build container, and before we install anything
	def record_package(self, sdist):
		self.built_spec.package_name = sdist.name
		self.build_info = self.built_spec.add_version(sdist.version)

	# This is called after we've unpacked a git repo
	def record_source(self, sdist):
		self.sdist = sdist
		self.build_info.add_source(sdist)

	def unpack(self, build_spec, sdist):
		self.record_package(sdist)

		engine = self.engine
		if engine.use_proxy:
			self.http_proxy = engine.config.globals.http_proxy

		# install additional packages as requested by build-info
		# Note: build_spec.dependencies covers all dependencies
		# from the defaults section, plus the ones specific to the
		# version we're just building
		for req in build_spec.dependencies:
			self.install_requirement(req)

		for src_index in range(len(build_spec.sources)):
			sdist = build_spec.sources[src_index]

			destdir = self.get_unpack_directory(sdist, cleanup = True)

			if sdist.git_url():
				self.unpack_git(sdist, destdir)
			else:
				self.unpack_archive(sdist, destdir)

			if src_index == 0:
				self.record_source(sdist)

			directory = self.compute.get_directory(destdir)
			if not directory or not directory.isdir():
				raise ValueError("Unpacking %s failed: cannot find %s" % (sdist.id(), destdir))

			if src_index == 0:
				self.directory = directory

				if build_spec.patches:
					self.apply_patches(build_spec)

	def get_unpack_directory(self, sdist, cleanup = False):
		if sdist.git_url():
			url = sdist.git_url()
			url = url.rstrip('/')
			relative_dir = url.split('/')[-1]
		else:
			relative_dir = self.archive_get_unpack_directory(sdist)

		if cleanup:
			d = self.build_base.lookup(relative_dir)
			if d is not None:
				d.rmtree()

		return os.path.join(self.build_base.path, relative_dir)

	def unpack_archive(self, sdist, destdir):
		archive = sdist.local_path
		if not archive or not os.path.exists(archive):
			raise ValueError("Unable to unpack %s: you need to download the archive first" % sdist.filename)

		shutil.unpack_archive(archive, self.build_base.hostpath())
		print("Unpacked %s to %s" % (archive, destdir))

	def unpack_git(self, sdist, destdir):
		repo_url = sdist.git_url()
		if not repo_url:
			raise ValueError("Unable to build from git - cannot determine git url")

		tag = sdist.git_tag()

		tag = self.unpack_git_helper(repo_url, tag, destdir = destdir, version_hint = str(sdist.version))
		print("Unpacked %s to %s" % (repo_url, destdir))

		sdist.git_repo_tag = tag

	# General helper function: clone a git repo to the given destdir, and
	# optionally check out the tag requested (HEAD otherwise)
	def unpack_git_helper(self, git_repo, tag = None, destdir = None, version_hint = None):
		assert(destdir) # for now

		if destdir:
			self.compute.run_command("git clone %s %s" % (git_repo, destdir))
		else:
			self.compute.run_command("git clone %s" % (git_repo))

		if tag is None and version_hint:
			tag = self.guess_git_tag(destdir, version_hint)
			if tag is None:
				raise ValueError("Unable to find a tag corresponding to version %s" % version_hint)

		if tag:
			self.compute.run_command("git checkout --detach %s" % tag, working_dir = destdir)

		return tag

	def guess_git_tag(self, destdir, version_hint):
		tag_canditates = (
			version_hint,
			version_hint.replace('.', '_'),
			)
		f = self.compute.popen("git tag", working_dir = destdir)
		for tag in f.readlines():
			tag = tag.strip()
			for tail in tag_canditates:
				if not tag.endswith(tail):
					continue

				head = tag[:-len(tail)]
				if head and (head[-1].isdigit() or head[-1] == '.'):
					# 12.1 is not a valid tag for version 2.1
					continue

				# the tag equals the (possibly transformed) version number,
				# possibly prefixed with a string that does not end with a
				# digit.
				print("Found tag %s for version %s" % (tag, version_hint))
				return tag

		return None

	def install_extra_file(self, local_path):
		shutil.copy(local_path, self.build_base.hostpath())

		return os.path.join(self.build_base.path, os.path.basename(local_path))

	def apply_patches(self, build_spec):
		for patch in build_spec.patches:
			print("Applying patch %s" % patch)
			pipe = self.compute.popen("patch -p1", mode = 'w', working_dir = self.directory.path)
			with open(patch, "r") as pf:
				data = pf.read()
				pipe.write(data)

			if pipe.close():
				raise ValueError("patch command failed (%s)" % patch)

	def build(self, build_strategy):
		for req_string in build_strategy.build_dependencies(self):
			print("build strategy requires %s" % req_string)

			req = self.engine.parse_build_requirement(req_string)

			# FIXME: check list of installed packages to see whether we
			# really need this
			# if not engine.dependency_already_satisfied(req):
			self.install_requirement(req)

			self.build_info.requires.append(req)

		for cmd in build_strategy.next_command(self):
			self.build_command_helper(cmd)

		return self.collect_build_results()

	def build_from_script(self, build_script):
		print("build_from_script(%s)" % build_script)
		path = self.install_extra_file(build_script)

		self.compute.run_command("/bin/sh -c %s" % path, working_dir = self.directory.path)

		# Record the fact that we used a build script (for now)
		self.build_info.build_script = build_script

	def build_command_helper(self, cmd):
		assert(self.directory)

		if self.build_log:
			log = open(self.build_log, "a")

			if not isinstance(cmd, ShellCommand):
				cmd = ShellCommand(cmd)

			if cmd.working_dir is None:
				cmd.working_dir = self.directory

			if self.http_proxy:
				pass

			# Set any other defaults, like the build user?

			f = self.compute.exec(cmd, mode = 'r')

			line = f.readline()
			while line:
				if not self.quiet:
					print(line.rstrip())
				log.write(line)

				line = f.readline()

			log.close()

			print("Command output written to %s" % self.build_log)

			if f.close():
				raise BuildFailure("Command `%s' returned non-zero exit status" % cmd, cmd)
		else:
			cmd += " >/dev/null 2>&1"
			self.compute.run_command(cmd, working_dir = self.directory)

	def unchanged_from_previous_build(self, build_state):
		self.mni()

	def has_build_dependency(self, name, engine_name = None):
		if engine_name == None:
			engine_name = self.engine.name
		for dep in self.build_info.requires + self.explicit_requirements_installed:
			if dep.engine == engine_name and dep.name == name:
				return True
		return False

	def guess_build_dependencies(self, build_strategy = None):
		self.mni()

	def finalize_build_depdendencies(self, downloader):
		self.mni()

	def prepare_results(self, build_state):
		self.save_build_info(build_state.get_new_path("build-info"))

		for build in self.build_info.artefacts:
			build.local_path = build_state.save_file(build.local_path)

	def save_build_info(self, info_path):
		self.built_spec.save(info_path)

	def build_requires_as_string(self):
		self.mni()

	def unchanged_from_previous_build(self, build_state):
		if not build_state.exists():
			print("%s was never built before" % self.sdist.id())
			return False

		samesame = True
		for build in self.build_info.artefacts:
			artefact_name = os.path.basename(build.local_path)

			if build.is_source:
				print("Not checking %s..." % (artefact_name))
				continue

			new_path = build.local_path
			old_path = build_state.get_old_path(artefact_name)
			print("Checking %s vs %s" % (new_path, old_path))
			if not os.path.exists(old_path):
				print("%s does not exist" % old_path)
				samesame = False
				continue

			if not self.artefacts_identical(old_path, new_path):
				print("%s differs from previous build" % artefact_name)
				samesame = False
				continue

		path = build_state.get_old_path("build-info")
		if not os.path.exists(path):
			print("Previous build of %s did not write a build-info file" % self.sdist.id())
			samesame = False
		else:
			new_path = build_state.get_new_path("build-info")

			with open(path, "r") as old_f:
				with open(new_path, "r") as new_f:
					if old_f.read() != new_f.read():
						print("Build info changed")
						run_command("diff -u %s %s" % (path, new_path), ignore_exitcode = True)
						samesame = False

		return samesame

	def artefacts_identical(self, old_path, new_path):
		def print_delta(path, how, name_set):
			print("%s: %s %d file(s)" % (path, how, len(name_set)))
			for name in name_set:
				print("  %s" % name)

		result = self.compare_build_artefacts(old_path, new_path)

		if result:
			print("%s: unchanged" % new_path)
			return True

		result.print()
		return False

	def compare_build_artefacts(self, old_path, new_path):
		self.mni()

	def install_requirement(self, req):
		engine = self.engine

		if req.engine != engine.name:
			engine = Engine.factory(req.engine)

		pkg = engine.install_requirement(self.compute, req)
		if pkg:
			self.explicit_requirements_installed.append(pkg)

		return pkg

class BuildState(Object):
	def __init__(self, engine, savedir):
		import tempfile

		self.engine = engine
		self.savedir = savedir
		self.tmpdir = tempfile.TemporaryDirectory(prefix = "brcoti-")

	def __del__(self):
		self.cleanup()

	def exists(self):
		return os.path.exists(self.savedir)

	def build_log_file(self):
		return os.path.join(self.tmpdir.name, "build.log")

	def commit(self):
		if not self.tmpdir:
			print("%s: changes already committed" % self.savedir)
			return

		# Clean up the savedir
		if os.path.exists(self.savedir):
			shutil.rmtree(self.savedir)
		os.makedirs(self.savedir, mode = 0o755)

		# And copy our data over it
		print("Committing build state to %s:" % self.savedir, end = ' ')
		for file in glob.glob(os.path.join(self.tmpdir.name, "*")):
			print(os.path.basename(file), end = ' ')
			shutil.copy(file, self.savedir)
		print("")

	def cleanup(self):
		if self.tmpdir:
			del self.tmpdir
		self.tmpdir = None

	def get_old_path(self, name):
		return os.path.join(self.savedir, name)

	def get_new_path(self, name):
		return os.path.join(self.tmpdir.name, name)

	def maybe_save_file(self, src, dst = None):
		if not os.path.exists(src):
			print("Not saving %s (does not exist)" % src)
			return None

		return self.save_file(src, dst)

	def save_file(self, src):
		dst = self.tmpdir.name

		print("Saving %s to %s" % (src, dst))

		if isinstance(src, ComputeResourceFS):
			src = src.hostpath()
		shutil.copy(src, dst)

		if os.path.isdir(dst):
			return os.path.join(dst, os.path.basename(src))
		return dst

	def write_file(self, name, data, desc = None):
		with self.open_file(name, desc) as f:
			f.write(data)

	def open_file(self, name, desc = None):
		path = self.get_new_path(name)

		if desc:
			print("Writing %s to %s" % (desc, path))
		else:
			print("Writing %s" % path)
		return open(path, "w")

	def get_old_build_used(self):
		for name in ("build-used", "build-info"):
			path = self.get_old_path(name)
			if os.path.exists(path):
				return path

		return None

	def built_previously(self):
		if not self.exists():
			return False
		path = self.get_old_build_used()
		return path is not None

	def rebuild_required(self):
		path = self.get_old_build_used()
		if not path:
			print("Previous build did not create a build-used file")
			return True

		try:
			engine = self.engine
			build_info = BuildSpec.from_file(path, default_engine = engine)
		except Exception as e:
			print("Cannot parse build-info file at %s" % path)
			print(e)
			return True

		for req in build_info.requires:
			if self.build_changed(req):
				return True

		return False

	def build_changed(self, req):
		print("Build requires %s" % req)

		p = self.engine.resolve_build_requirement(req)

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

class Publisher(Object):
	def __init__(self, type, repconfig):
		self.type = type
		self.repoconfig = repconfig

	class Fileset:
		def __init__(self):
			self._files = dict()
			self.dupes = []

		def add(self, path):
			name = os.path.basename(path)

			old_path = self._files.get(name)
			if old_path is not None:
				self.dupes.append(old_path)

			self._files[name] = path

		@property
		def artefacts(self):
			return self._files.values()

	def create_fileset(self):
		return self.Fileset()

	def rescan_state_dir(self, fileset, path):
		if not os.path.isdir(path):
			return

		print("Scanning %s for %s artefacts" % (path, self.type));
		for (dir_path, dirnames, filenames) in os.walk(path):
			for f in filenames:
				file_path = os.path.join(dir_path, f)
				if self.is_artefact(file_path):
					fileset.add(file_path)

	# TBD: implement a two-stage process where we first
	# create the updated hierarchy in a temporary location,
	# and then rename it to the final location (more or less
	# atomically).

	def commit(self):
		pass

	def prepare_repo_dir(self):
		path = self.repoconfig.url

		if not path.startswith("/"):
			raise ValueError("Cannot create publisher for URL \"%s\"" % path)

		if os.path.exists(path):
			shutil.rmtree(path)

		self.repo_dir = path
		os.makedirs(self.repo_dir, mode = 0o755)

		return path

	def prepare_repo_subdir(self, relative_path):
		path = os.path.join(self.repo_dir, relative_path)
		os.makedirs(path)
		return path

class ComputeResourceFS(Object):
	def __init__(self, path):
		self.path = path

	def __repr__(self):
		return self.path

	def basename(self):
		return os.path.basename(self.path)

	def rmtree(self):
		path = self.hostpath()
		if os.path.exists(path):
			print("Recursively remove %s" % path)
			shutil.rmtree(path)

	def hostpath(self):
		self.mni()

class ComputeResourceFile(ComputeResourceFS):
	def __init__(self, path):
		super(ComputeResourceFile, self).__init__(path)

	def open(self, mode = 'r'):
		self.mni()

	def isreg(self):
		return True

	def isdir(self):
		return False

class ComputeResourceDirectory(ComputeResourceFS):
	def __init__(self, path):
		super(ComputeResourceDirectory, self).__init__(path)

	def file_exists(self, path):
		self.mni()

	def lookup(self, path):
		self.mni()

	def open(self, path, mode = 'r'):
		self.mni()

	def glob_files(self, path_pattern):
		self.mni()

	def isreg(self):
		return False

	def isdir(self):
		return True

class ShellCommand(object):
	def __init__(self, cmd, working_dir = None, ignore_exitcode = False, privileged_user = False):
		if type(cmd) == str:
			self._cmd = [cmd]
		elif type(cmd) == list:
			self._cmd = cmd
		else:
			raise ValueError("ShellCommand: cmd must be str or list; never %s" % type(cmd))

		self.working_dir = working_dir
		self.ignore_exitcode = ignore_exitcode
		self.privileged_user = privileged_user

		# Hack for zypper
		self.no_default_env = False

		self.environ = {}

	def __repr__(self):
		s = self.cmd

		extra = []
		if self.working_dir:
			extra.append("cwd=%s" % self.working_dir)
		if self.privileged_user:
			extra.append("as_root")
		if extra:
			s += " (%s)" % (", ".join(extra))

		return s

	def add_args(self, *args):
		self._cmd += args

	@property
	def cmd(self):
		return ' '.join(self._cmd)

	def setenv(self, var_name, var_value):
		self.environ[var_name] = var_value

class ComputeNode(Object):
	def __init__(self, backend):
		self.backend = backend
		self.cleanup_on_exit = True

	def noclean(self):
		self.cleanup_on_exit = False

	def default_build_dir(self):
		return self.backend.default_build_dir()

	def translate_url(self, url):
		return url

	def trusted_hosts(self):
		return []

	def putenv(self, name, value):
		self.mni()

	def interactive_shell(self, working_directory = None):
		self.mni()

	def exec(self, shellcmd, mode = None):
		print("Running %s" % shellcmd)

		# Avoid messing up the order of our output and the output of subprocesses when
		# stdout is redirected
		sys.stdout.flush()
		sys.stderr.flush()

		# popen() behavior: return an open file object that is connected to
		# the commands stdout or stdin
		if mode is not None:
			return self._exec(shellcmd, mode)

		exit_code = self._exec(shellcmd, mode)

		if exit_code != 0 and not shellcmd.ignore_exitcode:
			raise ValueError("Command `%s' returned non-zero exit status" % shellcmd)

		return exit_code

	def run_command(self, cmd, working_dir = None, ignore_exitcode = False, privileged_user = False):
		shellcmd = ShellCommand(cmd, working_dir = working_dir, ignore_exitcode = ignore_exitcode, privileged_user = privileged_user)
		return self.exec(shellcmd)

	def _exec(self, shellcmd):
		self.mni()

	def popen(self, cmd, mode = 'r', working_dir = None, privileged_user = False):
		shellcmd = ShellCommand(cmd, working_dir = working_dir, privileged_user = privileged_user)
		return self.exec(shellcmd, mode)

	def get_directory(self, path):
		self.mni()

	def shutdown(self):
		self.mni()


class Compute(Object):
	def __init__(self, global_config, config):
		self.global_config = global_config
		self.config = config

	def default_build_dir(self):
		if self.config.build_dir is None:
			raise ValueError("Environment %s does not define a build_dir" % self.config.name)
		return self.config.build_dir

	def spawn(self, config, flavor):
		self.mni()

	@staticmethod
	def factory(name, config):
		print("Create %s compute backend" % name)

		env = config.get_environment(name)
		if env.type == 'local':
			import brcoti_local

			return brcoti_local.compute_factory(config, env)

		if env.type == 'podman':
			import brcoti_podman

			return brcoti_podman.compute_factory(config, env)

		raise NotImplementedError("Compute environment \"%s\" uses type \"%s\" - not implemented" % (name, env.type))

class Config(object):
	class ConfigItem:
		def __init__(self, config, d):
			if d is None:
				d = {}
			for f in self._fields:
				setattr(self, f, d.get(f))

			self._config = config

		def update(self, other):
			for f in self._fields:
				if getattr(self, f) is not None:
					continue
				setattr(self, f, getattr(other, f))

		def __repr__(self):
			return ", ".join(["%s=%s" % (f, getattr(self, f)) for f in self._fields])

	class Globals(ConfigItem):
		_fields = ('binary_root_dir', 'source_root_dir', 'binary_extra_dir', 'certificates', 'http_proxy')

		def __init__(self, config, d):
			super(Config.Globals, self).__init__(config, d)

	class Engine(ConfigItem):
		_fields = ('name', 'type', 'config')

		def __init__(self, config, d):
			super(Config.Engine, self).__init__(config, d)

		def get_value(self, config_key):
			return self.config.get(config_key)

		def resolve_repository(self, config_key):
			repo_id = self.get_value(config_key)
			if repo_id is None:
				return None

			return self._config.get_repository(self.type, repo_id)

	class Repository(ConfigItem):
		_fields = ('type', 'name', 'url', 'user', 'password', 'credentials', 'repotype')

		def __init__(self, config, d):
			super(Config.Repository, self).__init__(config, d)

		def require_credentials(self):
			if self.user and self.password:
				return

			if self.credentials is None:
				raise ValueError("Authentication required for repository %s/%s, but credentials are incomplete" % (
						self.type, self.name))

			creds = self._config._get_credentials(self.credentials)
			if creds is None:
				raise ValueError("Repository %s/%s references unknown credentials \"%s\"" % (
						self.type, self.name, self.credentials))

			if self.user is None:
				self.user = creds.user
			if self.password is None:
				self.password = creds.password

	class Credential(ConfigItem):
		_fields = ('name', 'user', 'password')

		def __init__(self, config, d):
			super(Config.Credential, self).__init__(config, d)

	class Image(ConfigItem):
		_fields = ('name', 'image')

		def __init__(self, config, d):
			super(Config.Image, self).__init__(config, d)

	class Network(ConfigItem):
		_fields = ('name', 'routing')

		def __init__(self, config, d):
			super(Config.Network, self).__init__(config, d)

	class Pod(ConfigItem):
		_fields = ('name', )

		def __init__(self, config, d):
			super(Config.Pod, self).__init__(config, d)

	class Environment(ConfigItem):
		_fields = ('name', 'type', 'build_dir', 'images', 'network', 'pod')

		def __init__(self, config, d):
			super(Config.Environment, self).__init__(config, d)

			self.images = config._to_list(self.images, Config.Image)
			self.network = config._to_object(self.network, Config.Network)
			self.pod = config._to_object(self.pod, Config.Pod)

		def get_image(self, flavor):
			for img in self.images:
				if img.name == flavor:
					return img

			raise ValueError("Environment \"%s\" does not define an image for \"%s\"" % (self.name, flavor))

	_signature = {
		'globals' : lambda self, o: Config._to_object(self, o, Config.Globals),
		'engines' : lambda self, o: Config._to_list(self, o, Config.Engine),
		'repositories' : lambda self, o: Config._to_list(self, o, Config.Repository),
		'credentials' : lambda self, o: Config._to_list(self, o, Config.Credential),
		'environments' : lambda self, o: Config._to_list(self, o, Config.Environment),
	}

	the_instance = None

	def __init__(self, cmdline_opts):
		assert(Config.the_instance is None)
		Config.the_instance = self

		self.command_line_options = cmdline_opts

		self.configs = []

		self.globals = Config.Globals(self, {})
		self.engines = []
		self.credentials = []
		self.repositories = []
		self.environments = []

	def load_file(self, path):
		if not os.path.exists(path):
			return
		with open(path, 'r') as f:
			import json

			d = json.load(f)

			for key, f in self._signature.items():
				raw = d.get(key)
				if raw is None:
					continue

				cooked = f(self, raw)
				if cooked is None:
					continue

				value = getattr(self, key)
				if type(value) == list:
					assert(type(cooked) == list)
					setattr(self, key, value + cooked)
				elif isinstance(value, Config.ConfigItem):
					value.update(cooked)
				else:
					setattr(self, key, cooked)

			self.configs.append(d)

		self._check_list(self.engines, ('name', 'type'))
		self._check_list(self.repositories, ('name', 'type', 'url'))
		self._check_list(self.credentials, ('name', ))

	def get_engine(self, name):
		for e in self.engines:
			if e.name == name:
				return e
		raise ValueError("Unknown build engine \"%s\"" % name)

	def get_environment(self, name):
		for e in self.environments:
			if e.name == name:
				return e
		raise ValueError("Unknown environment \"%s\"" % name)

	def get_repository(self, type, name):
		for r in self.repositories:
			if r.type != type and r.type != 'any':
				continue
			if r.name == name:
				return r
		raise ValueError("No repository named \"%s\" for engine type \"%s\"" % (name, type))

	def _get_credentials(self, name):
		for c in self.credentials:
			if c.name == name:
				return c
		return None

	def get_credentials(self, name):
		creds = self._get_credentials(name)
		if creds is None:
			raise ValueError("No credentials for \"%s\"" % name)
		return creds

	def get_repo_user(self, repo_config):
		user = repo_config.user
		if user is None and repo_config.credentials is not None:
			user = self.get_credentials(repo_config.credentials).user
		return user

	def get_repo_password(self, repo_config):
		password = repo_config.password
		if password is None and repo_config.credentials is not None:
			password = self.get_credentials(repo_config.credentials).password
		return password

	@staticmethod
	def _check_list(l, required_attrs):
		for obj in l:
			for k in required_attrs:
				if getattr(obj, k) is None:
					raise ValueError("%s config lacks required %s attribute" % (type(obj).__name__, k))

	def _to_list(self, json_list, T):
		if json_list is None:
			return

		return [T(self, item) for item in json_list]

	def _to_object(self, json_dict, T):
		return T(self, json_dict)

		result = []
		for item in json_list:
			for f in T._fields:
				if item.get(f) is None:
					item[f] = None

			obj = T(self, item)
			result.append(obj)
		return result

	@staticmethod
	def _to_namedtuple(d, nt):
		return nt(*[d.get(name) for name in nt._fields])

class Engine(Object):
	type = 'NOT SET'

	def __init__(self, engine_config):
		self.name = engine_config.name

		# This should go away at some point
		self.config = Config.the_instance
		config = Config.the_instance

		self.engine_config = engine_config

		self.state_dir = os.path.join(config.globals.binary_root_dir, engine_config.name)
		self.binary_extra_dir = os.path.join(config.globals.binary_extra_dir, engine_config.name)
		self.source_dir = os.path.join(config.globals.source_root_dir, engine_config.name)

		self.index = self.create_index(engine_config)
		self.upstream_index = self.create_upstream_index(engine_config)
		self.downloader = self.create_downloader(engine_config)
		self.uploader = self.create_uploader(engine_config)
		self.publisher = self.create_publisher(engine_config)

		self.reset_indices()

	def reset_indices(self):
		self.default_index = self.index
		self.use_proxy = True

	def use_upstream(self):
		self.default_index = self.upstream_index
		self.use_proxy = False

	def create_index(self, engine_config):
		repo_config = engine_config.resolve_repository("download-repo")
		if repo_config is None:
			return None
			raise ValueError("No download-repo configured for engine \"%s\"" % engine_config.name)

		print("%s: download repo is %s" % (engine_config.name, repo_config.url))

		return self.create_index_from_repo(repo_config)

	def create_upstream_index(self, engine_config):
		repo_config = engine_config.resolve_repository("upstream-repo")
		if repo_config is None:
			return None
			raise ValueError("No upstream-repo configured for engine \"%s\"" % engine_config.name)

		print("%s: upstream repo is %s" % (engine_config.name, repo_config.url))

		return self.create_index_from_repo(repo_config)

	def create_publisher(self, engine_config):
		repo_config = engine_config.resolve_repository("publish-repo")
		if repo_config is None:
			return None
			raise ValueError("No publish-repo configured for engine \"%s\"" % engine_config.name)

		print("%s: publish repo is %s" % (engine_config.name, repo_config.url))
		return self.create_publisher_from_repo(repo_config)

	def create_downloader(self, engine_config):
		return Downloader()

	def create_uploader(self, engine_config):
		repo_config = engine_config.resolve_repository("upload-repo")
		if repo_config is None:
			print("%s: no upload repo defined" % (engine_config.name))
			return None

		repo_config.require_credentials()

		print("%s: upload repo is %s; user=%s" % (engine_config.name, repo_config.url, repo_config.user))
		return self.create_uploader_from_repo(repo_config)

	def create_binary_download_finder(self, req, verbose = True):
		self.mni()

	def create_source_download_finder(self, req, verbose = True):
		self.mni()

	def create_requirement_set(self):
		return EngineSpecificRequirementSet()

	#
	# This method validates the explicit requirements specified in a build-spec
	# file, making sure that they can be resolved.
	# This helps to detect missing packages even before we've started up the
	# container.
	#
	def validate_build_spec(self, build_spec, auto_repair = False):
		# FIXME: use a RequirementSet

		# Note: build_spec.dependencies covers all dependencies
		# from the defaults section, plus the ones specific to the
		# version we're just building
		req_dict = {}
		for req in build_spec.dependencies:
			if req.engine == self.name:
				engine = self
			else:
				engine = Engine.factory(req.engine)

			req_list = req_dict.get(engine)
			if req_list is None:
				req_list = []
				req_dict[engine] = req_list

			req_list.append(req)

		missing = []

		for engine, req_list in req_dict.items():
			print("Explicit %s requirements given in build-spec:" % engine.name)
			for req in req_list:
				if req.origin:
					print("  %s (via %s)" % (req.format(), req.origin))
				else:
					print("  %s" % req.format())

			# See if we can resolve all requirements (and any packages pulled in via runtime
			# requirements).
			# If auto_repair was given, this will try to merge any missing packages
			# from upstream and stick them into the extra-binaries repo.
			missing += engine.validate_build_requirements(req_list, merge_from_upstream = auto_repair, recursive = True)

		if missing:
			sdist = build_spec.sources[0]
			raise UnsatisfiedDependencies("Build of %s has unsatisfied dependencies" % sdist.id(), missing)

	# Returns a ComputeNode instance
	def prepare_environment(self, compute_backend, build_spec):
		compute = compute_backend.spawn(self.engine_config.name)

		if self.use_proxy and self.config.globals.http_proxy:
			proxy = self.config.globals.http_proxy
			compute.putenv('http_proxy', proxy)
			compute.putenv('HTTP_PROXY', proxy)
			compute.putenv('https_proxy', proxy)

		return compute

	def downloader(self):
		return Downloader()

	def uploader(self):
		self.mni()

	@staticmethod
	def create_source_from_local_directory(path, config):
		path = path.rstrip('/')
		return SourceDirectory(path, config)

	# This is NOT a static method; the caller must first instantiate the engine that
	# is adequate for the source artefact they want to build.
	#
	# FUTURE: try to guess the language by peering inside the archive
	def create_source_from_local_file(self, path):
		sdist = self.create_artefact_from_local_file(path)
		if not sdist.is_source:
			raise ValueError("cannot build %s: not a source distribution" % path)
		return SourceFile(sdist)

	def create_artefact_from_local_file(self, path):
		self.mni()

	# This is currently somewhat limited and there are lots of assertions.
	# This code needs cleanup up and unification with the git url handling
	# code of eg the Ruby engine.
	def create_artefact_from_url(self, url, package_name = None, version = None, tag = None):
		import urllib.parse

		url, frag = urllib.parse.urldefrag(url)

		parsed_url = urllib.parse.urlparse(url)

		# For now, we only deal with github
		assert(parsed_url.hostname == 'github.com')

		if frag:
			assert(frag.startswith('version='))
			version = frag[8:]

		if parsed_url.query:
			for kvp in parsed_url.query.split('&'):
				(key, value) = kvp.split('=')
				if key == 'version':
					version = value
				elif key == 'tag':
					tag = value
				elif key == 'name':
					package_name = value
				else:
					raise ValueError("Invalid parameter %s in URL \"%s\"" % (kvp, url))

			url = urllib.parse.urlunparse(parsed_url._replace(query=''))

		if version is None:
			raise ValueError("Error when parsing URL \"%s\": no version given" % (url))

		if package_name is None:
			# github URLs are scheme:github.com/user_or_group/reponame/gobbledigook
			path = parsed_url.path.strip('/').split('/')
			assert(len(path) == 2)
			package_name = path[1]

		sdist = self.create_artefact_from_NVT(package_name, version, 'source')
		sdist.git_repo_url = url
		sdist.git_repo_tag = tag

		return sdist

	def create_artefact_from_NVT(self, name, version, type):
		self.mni()

	def infer_build_requirements(self, sdist):
		self.mni()

	def build_source_locate(self, req, verbose = True):
		finder = self.create_source_download_finder(req, verbose)
		return finder.get_best_match(self.default_index)

	def build_source_locate_upstream(self, req, verbose = True):
		finder = self.create_source_download_finder(req, verbose)
		return finder.get_best_match(self.upstream_index)

	def build_state_factory(self, sdist):
		savedir = self.build_state_path(sdist.id())
		return BuildState(self, savedir)

	def build_state_path(self, artefact_name):
		return os.path.join(self.state_dir, artefact_name)

	def publish_build_results(self, prune_extras = False):
		publisher = self.publisher
		if not publisher:
			raise ValueError("%s: no publisher" % self.name)

		publisher.prepare()

		fileset = publisher.create_fileset()

		publisher.rescan_state_dir(fileset, self.binary_extra_dir)
		publisher.rescan_state_dir(fileset, self.state_dir)

		if prune_extras and fileset.dupes:
			print("Found %d duplicates" % len(fileset.dupes))
			for p in fileset.dupes:
				print("  " + p)

			for p in fileset.dupes:
				os.remove(p)

		for path in fileset.artefacts:
			publisher.publish_artefact(path)

		publisher.finish()
		publisher.commit()

		if self.index:
			self.index.zap_cache()

	def create_build_strategy_default(self):
		self.mni()

	def create_build_strategy_from_script(self, path):
		return BuildStrategy_FromScript(path)

	def create_build_strategy(self, name, *args):
		if name == 'script':
			return BuildStrategy_FromScript(*args)

		raise ValueError("%s: unknown build strategy \"%s\"" % (self.name, name))

	def finalize_build_depdendencies(self, build):
		for req in build.build_info.requires:
			missing = []
			for algo in self.REQUIRED_HASHES:
				if req.get_hash(algo) is None:
					missing.append(algo)

			if not missing:
				continue

			# FIXME: the proxy cache should tell us exactly what got downloaded in order
			# to build the package
			print("%s: update missing hash(es): %s" % (req.id(), " ".join(missing)))

			resolved_req = req.resolution
			if not resolved_req:
				resolved_req = self.resolve_build_requirement(req)
			if not resolved_req:
				raise ValueError("Unable to resolve build dependency %s" % req.name)

			# resolve_build_requirement() goes to an index, and should hence
			# always attach a cache object
			assert(resolved_req.cache)

			self.downloader.download(resolved_req)

			for algo in missing:
				resolved_req.update_hash(algo)
				req.add_hash(algo, resolved_req.hash[algo])

		return build.build_info.requires

	def create_empty_requirement(self, name):
		self.mni()

	def parse_build_requirement(self, req_string):
		self.mni()

	# Given a build requirement, find the best match in the package index
	def resolve_build_requirement(self, req, verbose = False):
		finder = self.create_binary_download_finder(req, verbose)
		return finder.get_best_match(self.default_index)

	# Given a (binary) artefact, return its installation dependencies
	def resolve_install_requirements(self, artefact):
		if not self.downloader:
			return []

		assert(artefact.cache)
		self.downloader.download(artefact, quiet = True)
		return artefact.get_install_requirements()

	# Given a list of build requirements, check our index to see whether they
	# can be satisified. Return a list of unsatisfied dependencies
	def resolve_build_requirement_list(self, requirements, recursive = False, resolved = None):
		if not requirements:
			return

		# Turn the list of requirements into a set
		if type(requirements) != set:
			requirements = set(requirements)

		missing = set()

		seen = set()
		while requirements:
			req = requirements.pop()

			if req.format() in seen:
				continue
			seen.add(req.format())

			try:
				found = self.resolve_build_requirement(req, verbose = False)
				assert(found)
			except:
				missing.add(req)
				continue

			if resolved is not None:
				resolved.append(found)

			transitive = []
			if recursive:
				transitive = self.resolve_install_requirements(found)

			if transitive:
				print("  %s resolved to %s, which requires %s" % (req.format(), found.id(),
							"|".join([req.format() for req in transitive])))
			else:
				print("  %s resolved to %s" % (req.format(), found.id()))

			requirements.update(transitive)

		return missing

	# Given a list of build requirements, check our index to see whether they
	# can be satisified. Return a list of unsatisfied dependencies
	def validate_build_requirements(self, requirements, merge_from_upstream = True, recursive = False):
		if not requirements:
			return

		print("Trying to resolve build requirements%s" % (recursive and " recursively" or ""))

		# Turn the list of requirements into a set
		requirements = set(requirements)
		merged_some = False

		while requirements:
			missing = self.resolve_build_requirement_list(requirements, recursive)

			if not merge_from_upstream:
				break
			elif missing:
				self.merge_from_upstream(missing, requirements, update_index = False)
				merged_some = True

		if merged_some:
			self.publish_build_results()

		if not missing:
			print("Looks like we're able to satisfy all dependencies, let's go ahead")

		return missing

	def validate_used_packages(self, used, merge_from_upstream = True):
		name_match = []
		no_match = []
		missing = []

		if not used:
			return

		print("Checking %d package(s) that were installed from upstream during build" % len(used))

		for artefact in used:
			req = self.parse_build_requirement("%s == %s" % (artefact.name, artefact.version))

			# See if we have an exact match
			try:
				found = self.resolve_build_requirement(req, verbose = False)
				if found:
					continue
			except:
				pass

			# See if we have any version of this package
			try:
				found = self.resolve_build_requirement(artefact.name, verbose = False)
				if found:
					name_match.append(artefact)
					continue
			except:
				pass

			no_match.append(artefact)
			missing.append(req)

		if name_match:
			print("The following packages exist in our index, but with a different version:")
			for artefact in name_match:
				print("  %s" % artefact.id())

		if missing:
			print("The following packages are not present in our index at all:")
			for artefact in no_match:
				print("  %s" % artefact.id())

			if merge_from_upstream:
				print("Trying to merge them from upstream")
				missing = self.merge_from_upstream(missing)

		return missing

	def merge_from_upstream(self, missing_deps, requirements = None, update_index = True):
		# Not all engines support merging missing packages from upstream. For example,
		# the rpm engine pulls from opensuse.org and that's it.
		return missing_deps

	# We could also replace this by setting
	#  Engine.buildDirectoryClass = {Ruby,Python,...}BuildDirectory
	def create_build_directory(self, compute):
		self.mni()

	# This is for the comparison of the artefacts we built with upstream
	# Some engines (like ruby) may decide to compile extensions, in which case
	# there may be no exact upstream build.
	# In this case, the engine would reimplement this method, and return None
	# for those artefacts it won't compare.
	def get_upstream_build_for(self, sdist, artefact):
		req_string = "%s == %s" % (sdist.name, sdist.version)

		print("Trying to find upstream build for %s" % req_string)
		req = self.parse_build_requirement(req_string)

		finder = self.create_binary_download_finder(req, verbose = False)
		upstream = finder.get_best_match(self.upstream_index)
		if not upstream:
			raise ValueError("No upstream build for %s" % req_string)

		print("upstream %s platform %s" % (upstream.id(), upstream.platform))
		return upstream

	def submit_source(self, source):
		name = os.path.basename(source.path)
		assert(name and not name.startswith('.'))

		dest_path = os.path.join(self.source_dir, name)
		if os.path.exists(dest_path):
			print("Remove %s" % dest_path)
			shutil.rmtree(dest_path)

		print("Copying %s to %s" % (source.path, dest_path))
		os.makedirs(dest_path, 0o755)

		for file in glob.glob(source.path + "/*"):
			print("  %s -> %s" % (file, dest_path))
			shutil.copy(file, dest_path)

	engine_cache = {}

	@staticmethod
	def factory(name):
		engine = Engine.engine_cache.get(name)
		if engine is not None:
			return engine

		if Config.the_instance is None:
			print("Engine.factory called before a config file was loaded. This will not work.")
			raise ValueError

		config = Config.the_instance

		print("Create %s builder" % name)
		engine_config = config.get_engine(name)

		print("%s: using %s engine" % (name, engine_config.type))
		if engine_config.type == 'python':
			import brcoti_python

			engine = brcoti_python.engine_factory(engine_config)
		elif engine_config.type == 'ruby':
			import brcoti_ruby

			engine = brcoti_ruby.engine_factory(engine_config)
		elif engine_config.type == 'rpm':
			import brcoti_rpm

			engine = brcoti_rpm.engine_factory(engine_config)
		else:
			raise NotImplementedError("No build engine for \"%s\"" % name)

		Engine.engine_cache[name] = engine
		return engine
