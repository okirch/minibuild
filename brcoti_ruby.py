#
# rubygem specific portions of brcoti
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
import ruby_utils

import brcoti_core

ENGINE_NAME	= 'ruby'

def get_ruby_version():
	return os.popen("ruby -e 'print(RUBY_VERSION)'").read()

def get_rubygems_version():
	return os.popen("ruby -e 'print(Gem::VERSION)'").read()

def canonical_package_name(name):
	return name

class RubyBuildRequirement(brcoti_core.BuildRequirement):
	engine = ENGINE_NAME

	def __init__(self, name, req_string = None, cooked_requirement = None):
		super(RubyBuildRequirement, self).__init__(canonical_package_name(name), req_string, cooked_requirement)

	def parse_requirement(self, req_string):
		import ruby_utils

		self.cooked_requirement = ruby_utils.Ruby.parse_dependency(req_string)
		self.req_string = req_string

	@staticmethod
	def from_string(req_string):
		import ruby_utils

		cooked_requirement = ruby_utils.Ruby.parse_dependency(req_string)
		return RubyBuildRequirement(cooked_requirement.name, req_string, cooked_requirement)

	def __repr__(self):
		if self.cooked_requirement:
			return repr(self.cooked_requirement)
		if self.req_string:
			return self.req_string
		return self.name

	def format(self):
		if self.cooked_requirement:
			return self.cooked_requirement.format(include_attrs = False)
		if self.req_string:
			return self.req_string
		return self.name

class RubyArtefact(brcoti_core.Artefact):
	engine = ENGINE_NAME

	def __init__(self, name, version = None, type = None):
		super(RubyArtefact, self).__init__(canonical_package_name(name), version)

		self.type = type
		self.required_ruby_version = None
		self.required_rubygems_version = None

		self.filename = None

		self.gemspec = None

		# package info
		self.home_page = None
		self.author = None

	@property
	def is_source(self):
		return self.type == 'source'

	def verify_minimum_version(self, my_version, req_version):
		import ruby_utils

		if req_version is None:
			return True

		# print("verify_minimum_version(mine=%s, wanted=%s)" % (my_version, req_version))
		return my_version in req_version

	def verify_required_ruby_version(self):
		return self.verify_minimum_version(get_ruby_version(), self.required_ruby_version)

	def verify_required_rubygems_version(self):
		return self.verify_minimum_version(get_rubygems_version(), self.required_rubygems_version)

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
			_type = 'source'
		elif _suffix == "gem":
			_type = 'gem'
		else:
			raise ValueError("Unable to parse file name \"%s\"" % filename)

		return _name, _version, _type

	@staticmethod
	def from_local_file(path, name = None, version = None, type = None):
		filename = os.path.basename(path)

		if not name or not version or not type:
			# try to detect version and type by looking at the file name
			_name, _version, _type = RubyArtefact.parse_filename(filename)

			if name:
				assert(name == _name)
			name = _name
			if version:
				assert(version == _version)
			version = _version
			if type:
				assert(type == _type)
			type = _type

		build = RubyArtefact(name, version, type)
		build.filename = filename
		build.local_path = path

		for algo in RubyEngine.REQUIRED_HASHES:
			build.update_hash(algo)

		return build

	def read_gemspec_from_gem(self):
		assert(self.local_path)

		self.gemspec = GemFile(self.local_path).parse_metadata()

class RubyReleaseInfo(brcoti_core.PackageReleaseInfo):
	def __init__(self, name, version, parsed_version = None):
		super(RubyReleaseInfo, self).__init__(canonical_package_name(name), version)

		if not parsed_version:
			parsed_version = ruby_utils.Ruby.ParsedVersion(version)

		self.parsed_version = parsed_version

	def id(self):
		return "%s-%s" % (self.name, self.version)

	def more_recent_than(self, other):
		assert(isinstance(other, RubyReleaseInfo))
		return other.parsed_version < this.parsed_version

class RubyPackageInfo(brcoti_core.PackageInfo):
	def __init__(self, name):
		super(RubyPackageInfo, self).__init__(canonical_package_name(name))

class RubyDownloadFinder(brcoti_core.DownloadFinder):
	def __init__(self, req, verbose, cooked_requirement = None):
		super(RubyDownloadFinder, self).__init__(verbose)

		if type(req) != RubyBuildRequirement:
			req = RubyBuildRequirement.from_string(req)

		self.requirement = req.cooked_requirement
		self.name = req.name
		self.allow_prereleases = False

	def release_match(self, release):
		assert(release.parsed_version)
		if not self.allow_prereleases and release.parsed_version.is_prerelease:
			return False

		if (release.name, release.parsed_version) not in self.requirement:
			return False

		return True

	def get_best_match(self, index):
		info = index.get_package_info(self.name)

		if info is None:
			if self.verbose:
				print("%s not found in package index" % self.name)
			return None

		if self.verbose:
			print("%s versions: %s" % (self.name, ", ".join(info.versions())))

		best_match = None
		best_release = None

		releases = sorted(info.releases, key = lambda r: r.parsed_version)
		while releases and not best_match:
			best_release = releases.pop()

			if not self.release_match(best_release):
				if self.verbose:
					print("ignoring release %s" % best_release.id())
				continue

			# Create an artefact for the binary gem (by downloading the gemspec
			# from the index).
			# If possible, also create a source artefact by guessing the source
			# URL.
			index.get_gemspec(best_release)

			for build in best_release.builds:
				# print("%s: inspecting build %s (type %s)" % (release.id(), build.filename, build.type))
				if not build.verify_required_ruby_version():
					if self.verbose:
						print("ignoring build %s (requires ruby %s)" % (build.filename, build.required_ruby_version))
					continue

				if not build.verify_required_rubygems_version():
					if self.verbose:
						print("ignoring build %s (requires ruby gems %s)" % (build.filename, build.required_rubygems_version))
					continue

				good_match = build

				if not self.build_match(build):
					continue

				best_match = build
				break

			if good_match and not best_match:
				raise ValueError("%s: found release %s, but not the matching artefact type" % (self.name, best_release.version))

		if not best_match:
			raise ValueError("%s: unable to find a matching release" % self.name)

		if self.verbose:
			extra = ""
			if best_match.git_repo_url:
				extra += "; source repo at %s" % best_match.git_repo_url
			print("Best match for %s is %s %s%s" % (self.name, best_match.type, best_match.id(), extra))

		return best_match

class RubySourceDownloadFinder(RubyDownloadFinder):
	def __init__(self, req, verbose = False, cooked_requirement = None):
		super(RubySourceDownloadFinder, self).__init__(req, verbose, cooked_requirement)

	def build_match(self, build):
		if self.verbose:
			print("inspecting %s which is of type %s" % (build.filename, build.type))
			print("  git repo %s" % build.git_repo_url)

		return build.type == 'source'

class RubyBinaryDownloadFinder(RubyDownloadFinder):
	def __init__(self, req, verbose = False, cooked_requirement = None):
		super(RubyBinaryDownloadFinder, self).__init__(req, verbose, cooked_requirement)

	def build_match(self, build):
		if self.verbose:
			print("inspecting %s which is of type %s" % (build.filename, build.type))
		return build.type == 'gem'

class RubySpecIndex(brcoti_core.HTTPPackageIndex):
	def __init__(self, url):
		super(RubySpecIndex, self).__init__(url)

		# For some bizarre reason, the specs files are avaliable from nexus in different compression
		# formats, but the gemspec is only provided as zlib compressed file
		self._pkg_url_template = "{index_url}/quick/Marshal.4.8/{pkg_name}-{pkg_version}.gemspec.rz"

		self._cached_latest_specs = None
		self._cached_specs = None

	def get_package_info(self, name):
		pi = self.locate_gem(name, verbose = False)

		return pi

	def locate_gem(self, name, latest_only = False, verbose = True):
		# latest_specs.4.8 and specs.4.8 contain an array of info tuples.
		# Each tuple represents the (latest known) version of a gem, and consists of 3 elements:
		#  [name, Gem::Version(...), platform]
		# platform is usually "ruby", but can also be "java-something"
		if latest_only:
			gem_list = self._latest_specs()
		else:
			gem_list = self._specs()

		if verbose:
			print("Locating %s in %s" % (name, self.url))

		pi = RubyPackageInfo(name)
		for gem in gem_list:
			if gem[0] == name:
				version_list = gem[1]
				# weird. rubygems.org always gives us an array of versions,
				# but nexus seems to give us a single version object
				if isinstance(version_list, ruby_utils.Ruby.GemVersion):
					version = str(version_list)
				else:
					version = version_list[0]

				if gem[2] != 'ruby':
					# print("Warning: Cannot use %s-%s: platform is \"%s\"" % (name, version, gem[2]))
					continue

				release = RubyReleaseInfo(name, version)
				pi.add_release(release)

		if not pi.releases:
			raise ValueError("Gem \"%s\" not found in index" % name)

		return pi

	def _latest_specs(self):
		if self._cached_latest_specs is None:
			self._cached_latest_specs = self._download_and_parse_specs("latest_specs.4.8.gz")
		return self._cached_latest_specs

	def _specs(self):
		if self._cached_specs is None:
			self._cached_specs = self._download_and_parse_specs("specs.4.8.gz")
		return self._cached_specs

	def _download_and_parse_specs(self, filename):
		import urllib.request

		url = os.path.join(self.url, filename)

		print("Downloading index at %s" % url)
		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to download index %s: HTTP response %s (%s)" % (
					filename, resp.status, resp.reason))

		from ruby_utils import unmarshal

		# This is fairly slow... need to speed this up!
		return unmarshal(filename, resp)

	def get_gemspec(self, release):
		import urllib.request

		url = self._pkg_url_template.format(index_url = self.url, pkg_name = release.name, pkg_version = release.version)

		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to get package info for %s-%s: HTTP response %s (%s)" % (
					release.name, release.version, resp.status, resp.reason))

		self.process_gemspec_response(resp, release)

	def process_gemspec_response(self, resp, release):
		from ruby_utils import unmarshal

		gemspec = unmarshal(resp.url, resp)

		release.add_build(self.gemspec_to_binary(gemspec))

		build = self.gemspec_to_source(gemspec)
		if build:
			release.add_build(build)

	def gemspec_to_binary(self, gemspec):
		build = self.gemspec_to_build_common(gemspec, 'gem')

		build.filename = "%s-%s.gem" % (gemspec.name, gemspec.version)
		build.url = "%s/gems/%s" % (self.url, build.filename)
		return build

	def gemspec_to_source(self, gemspec):
		try_urls = []
		if gemspec.metadata:
			source_code_uri = gemspec.metadata.get('source_code_uri')
			if source_code_uri is not None:
				try_urls.append(source_code_uri)

		if gemspec.homepage:
			try_urls.append(gemspec.homepage)

		for url in try_urls:
			build = self.uri_to_source(gemspec, url)
			if build is not None:
				# print("  found %s" % build.url)
				return build

		return None

	def uri_to_source(self, gemspec, uri):
		if type(uri) != str:
			return None

		def try_archive_url(repo_uri):
			uri = repo_uri.rstrip('/')
			project_name = os.path.basename(uri) or gemspec.name
			uri = "%s/archive/v%s.tar.gz" % (uri, gemspec.version)
			if self.uri_exists(uri):
				build = self.gemspec_to_build_common(gemspec, 'source')
				build.filename = "%s-%s.tar.gz" % (project_name, gemspec.version)
				build.url = uri
				build.git_repo_url = repo_uri
				return build

		# print("Check if we can get source for %s from URI %s" % (gemspec.version, uri))
		if uri.startswith('https://github.com/') or \
		   uri.startswith('http://github.com/'):
			# railties metadata specifies a source_code_url of
			# https://github.com/rails/rails/tree/v6.0.3.4/railties
			needle = "/tree/v%s" % (gemspec.version,)
			if uri.endswith(needle):
				build = try_archive_url(uri[:-len(needle)])
				if build is not None:
					return build

			# sprockets-rails specifies a homepage of 
			# https://github.com/rails/sprockets-rails
			build = try_archive_url(uri)
			if build is not None:
				return build

		return None

	def gemspec_to_build_common(self, gemspec, build_type):
		build = RubyArtefact(gemspec.name, gemspec.version, type = build_type)
		build.required_ruby_version = gemspec.required_ruby_version
		build.required_rubygems_version = gemspec.required_rubygems_version

		build.filename = "%s-%s.gem" % (gemspec.name, gemspec.version)
		build.url = "%s/gems/%s" % (self.url, build.filename)

		build.author = gemspec.author
		build.homepage = gemspec.homepage

		if False:
			for attr_name in dir(gemspec):
				attr_val = getattr(gemspec, attr_name)
				if callable(attr_val) or attr_name.startswith('_'):
					continue
				print("%-20s = %s" % (attr_name, attr_val))

			for key, value in gemspec.metadata.items():
				print("metadata." + key, value)

		build.gemspec = gemspec
		return build

	def uri_exists(self, url):
		# Don't be a nuisance, avoid lots of HEAD requests against github.
		return True

		import urllib.request

		req = urllib.request.Request(url=url, method='HEAD')

		try:
			resp = urllib.request.urlopen(req)
			return resp.status == 200
		except:
			print("URI %s does not exist" % url)
			return False

# Upload package using "gem nexus"
# You need to have the nexus gem installed for this
class RubyUploader(brcoti_core.Uploader):
	def __init__(self, url, user, password):
		self.url = url
		self.config_written = False

		assert(user)
		assert(password)

		self.user = user
		self.password = password

	def describe(self):
		return "Ruby repository \"%s\"" % self.url

	def upload(self, build):
		assert(build.local_path)

		self.prepare_config()

		print("Uploading %s to %s repository" % (build.local_path, self.url))
		brcoti_core.run_command("gem nexus %s" % build.local_path)

	def prepare_config(self):
		if not self.config_written:
			import basicauth

			home = os.getenv("HOME")
			assert(home)
			path = os.path.join(home, ".gem", "nexus")

			with open(path, "w") as f:
				f.writelines("---\n:url: %s\n:authorization: %s\n" % (
					self.url,
					basicauth.encode(self.user, self.password)))

			self.config_written = True

class GemFile(object):
	def __init__(self, path):
		self.path = path

		self._tar = self.open()

	def open(self):
		import tarfile

		return tarfile.open(self.path, mode = 'r')

	@property
	def basename(self):
		return os.path.basename(self.path)

	def compare(self, other):
		return GemFile.do_compare(self, other)

	# Tune how serious some divergence of metadata actually is
	# We should make this configurable
	metadata_badness = {
		'date' : 0,
		'rubygems_version' : 0,
	}

	@staticmethod
	def do_compare(old, new, max_badness = 0):
		# First, compare the contents of data.tar.gz.
		# We only look at regular files contained in the tarfile, even though
		# we should probably also look at symlinks and hardlinks
		result = GemFile.compare_data(old, new)

		old_meta = old.parse_metadata()
		new_meta = new.parse_metadata()
		d = old_meta.diff(new_meta, GemFile.metadata_badness)
		if d.badness() > max_badness:
			result.changed.add("metadata")

			d.name = "metadata"
			result.add_differ(d)

		# Ignore checksums and signatures

		return result

	@staticmethod
	def compare_data(old, new):
		old_data_tar = old.get_data()
		new_data_tar = new.get_data()

		old_name_set = GemFile.tar_member_names(old_data_tar)
		new_name_set = GemFile.tar_member_names(new_data_tar)

		result = brcoti_core.ArtefactComparison(new.path)

		result.added = new_name_set - old_name_set
		result.removed = old_name_set - new_name_set

		for member_name in old_name_set.intersection(new_name_set):
			old_data = GemFile.get_member_data(old_data_tar, member_name)
			new_data = GemFile.get_member_data(new_data_tar, member_name)

			if new_data != old_data:
				result.changed.add(member_name)
				result.add_raw_data_differ(member_name, old_data, new_data)

		return result

	def get_data(self):
		import tarfile

		try:
			f = self._tar.extractfile("data.tar.gz")
		except:
			print("ERROR: %s does not contain data.tar.gz" % self.path)
			# Forces a mis-compare in the caller
			return self.path

		return tarfile.open(fileobj = f, mode = 'r:gz')

	@staticmethod
	def tar_member_names(tar_file):
		result = set()
		for member in tar_file.getmembers():
			if member.isfile():
				result.add(member.name)

		return result

	@staticmethod
	def get_member_data(tar_file, name):
		return tar_file.extractfile(name).read()

	def open_metadata(self):
		import gzip

		try:
			f = self._tar.extractfile("metadata.gz")
		except:
			print("ERROR: %s does not contain metadata.gz" % self.path)
			# Forces a mis-compare in the caller
			return self.path

		return gzip.GzipFile(fileobj = f, mode = 'r')

	def get_metadata(self):
		return self.open_metadata().read()

	def parse_metadata(self):
		io = self.open_metadata()
		return ruby_utils.Ruby.YAML.load(io)

class RubyBuildStrategy(brcoti_core.BuildStrategy):
	pass

class BuildStrategy_GemBuild(RubyBuildStrategy):
	_type = "gem-build"

	def __init__(self, name = None):
		super(BuildStrategy_GemBuild, self).__init__()
		self.name = name

	def describe(self):
		return '%s(%s)' % (self._type, self.name or "")

	def next_command(self, build_directory):
		if self.name:
			yield "gem build '%s.gemspec'" % self.name
		else:
			for spec in build_directory.directory.glob_files("*.gemspec"):
				yield "gem build '%s'" % os.path.basename(spec.path)

class BuildStrategy_GemCompile(RubyBuildStrategy):
	_type = "gem-compile"

	def __init__(self, inner_job, name = None):
		super(BuildStrategy_GemCompile, self).__init__()
		self.inner_job = inner_job
		self.name = name

	def describe(self):
		if self.name:
			return '%s(%s, %s)' % (self._type, self.inner_job.describe(), self.name)
		else:
			return '%s(%s)' % (self._type, self.inner_job.describe())

	def next_command(self, build_directory):
		for cmd in self.inner_job.next_command(build_directory):
			yield cmd

		if self.name:
			yield "gem compile '%s-*.gem'" % self.name
		else:
			for spec in build_directory.directory.glob_files("*.gem"):
				yield "gem compile '%s'" % os.path.basename(spec.path)

class BuildStrategy_Rake(RubyBuildStrategy):
	_type = "rake"

	def __init__(self, targets = ['build']):
		super(BuildStrategy_Rake, self).__init__()
		if type(targets) == str:
			targets = [targets]
		self.targets = targets

	def describe(self):
		return '%s(%s)' % (self._type, ", ".join(self.targets))

	def next_command(self, build_directory):
		# FIXME: should we try to detect supported rake tasks
		# if none were given?
		for tgt in self.targets:
			yield "rake %s" % tgt

class BuildStrategy_Bundler(RubyBuildStrategy):
	_type = "bundler"

	def __init__(self, inner_job):
		super(BuildStrategy_Bundler, self).__init__()
		self.inner_job = inner_job

	def describe(self):
		return '%s(%s)' % (self._type, self.inner_job.describe())

	def next_command(self, build_directory):
		# While we bootstrap ruby building, skip everything test related and go just for the build
		yield brcoti_core.ShellCommand('bundler install --full-index --without test', privileged_user = True)

		for cmd in self.inner_job.next_command(build_directory):
			yield "bundler exec " + cmd

	# TBD: run bundle package to collect the used gems into vendor/cache
	# and return them for inclusion in the build-info file

class BuildStrategy_Auto(RubyBuildStrategy):
	_type = "auto"

	def __init__(self):
		self.actual = None

	def describe(self):
		if self.actual:
			return self.actual.describe()
		return "auto"

	def next_command(self, build_directory):
		where = build_directory.directory

		strategy = None
		if where.lookup("Rakefile"):
			strategy = BuildStrategy_Rake()
		else:
			strategy = BuildStrategy_GemBuild()

		if where.lookup("Gemfile"):
			strategy = BuildStrategy_Bundler(strategy)

		for cmd in strategy.next_command(build_directory):
			yield cmd

		# TODO: now look at the results and see if they contain
		# a native extension. If so, compile than gem (and alter
		# our strategy)

		self.actual = strategy

class RubyBuildDirectory(brcoti_core.BuildDirectory):
	def __init__(self, compute, engine):
		super(RubyBuildDirectory, self).__init__(compute, compute.default_build_dir())

		self.build_info = brcoti_core.BuildInfo(engine.name)

	# Most of the unpacking happens in the BuildDirectory base class.
	# The only python specific piece is guessing which directory an archive is extracted to
	def archive_get_unpack_directory(self, sdist):
		name, version, type = RubyArtefact.parse_filename(sdist.filename)
		return name + "-" + version

	def infer_build_dependencies(self):
		loc = self.directory.lookup('Gemfile.lock')

		requirements = []
		if loc is not None:
			gemfile_lock = ruby_utils.Ruby.GemfileLock.parse(loc)

			print("Analyzing contents of Gemfile.lock")
			# gemfile_lock.dump()

			# gemfile_lock.requirements() returns a list of
			# GemDependency objects; we need to convert these into
			# RubyBuildRequirements
			for dep in gemfile_lock.requirements():
				requirements.append(RubyBuildRequirement(dep.name, dep.format(), dep))

		return requirements

	def collect_build_results(self):
		sdist = self.sdist
		gems = self.directory.glob_files("*.gem")

		pkgdir = self.directory.lookup("pkg")
		if pkgdir is not None:
			gems += pkgdir.glob_files("*.gem")

		print("Successfully built %s: %s" % (sdist.id(), ", ".join([w.basename() for w in gems])))
		for w in gems:
			w = w.hostpath()

			build = RubyArtefact.from_local_file(w)

			build.read_gemspec_from_gem()

			for algo in RubyEngine.REQUIRED_HASHES:
				build.update_hash(algo)

			self.build_info.add_artefact(build)

		return self.build_info.artefacts

	# Compare old build of a gem vs the current build. This method
	# is expected to return an ArtefactComparison object
	def compare_build_artefacts(self, old_path, new_path):
		return GemFile(old_path).compare(GemFile(new_path))

	# It would be better if we'd inspect the build log for the actual artefacts
	# used, rather than going through the spec index ourselves. However, for the
	# time being I don't know where to actually get this info from
	def guess_build_dependencies(self):
		from packaging.requirements import Requirement

		seen = dict()
		for build in self.build_info.artefacts + [self.sdist, ]:
			if not build.gemspec:
				if not build.is_source:
					print("Warning: no gemspec info for %s" % build.filename)
				continue

			self.add_build_dependencies_from_gemspec(build.gemspec, seen)

		return self.build_info.requires

	def add_build_dependencies_from_gemspec(self, gemspec, seen):
		# print("add_build_dependencies_from_gemspec(%s-%s)" % (gemspec.name, gemspec.version))
		for dep in gemspec.dependencies:
			req_string = dep.name + ",".join([str(x) for x in dep.requirement])
			# print("  %s %s" % (req_string, dep.type))
			if dep.type != 'development':
				continue

			req_string = dep.name + ",".join([str(x) for x in dep.requirement])
			if seen.get(req_string) is None:
				req = RubyBuildRequirement(dep.name, req_string = req_string, cooked_requirement = dep)
				self.build_info.add_requirement(req)
				seen[req_string] = req

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

class RubyPublisher(brcoti_core.Publisher):
	def __init__(self, repoconfig):
		super(RubyPublisher, self).__init__("ruby", repoconfig)

		self.gems = set()

	def prepare(self):
		self.prepare_repo_dir()

		self.gems_dir = self.prepare_repo_subdir("gems")

	def is_artefact(self, path):
		return path.endswith(".gem")

	def publish_artefact(self, path):
		print(" %s" % path)
		shutil.copy(path, self.gems_dir)

		path = os.path.join(self.gems_dir, os.path.basename(path))
		self.gems.add(path)

	def finish(self):
		cmd = "gem generate_index --directory %s" % self.repo_dir
		brcoti_core.run_command(cmd)

		self.create_compact_index()

	def create_compact_index(self):
		packages = {}

		for path in self.gems:
			build = RubyArtefact.from_local_file(path)
			build.read_gemspec_from_gem()
			if build.gemspec is None:
				raise ValueError("Unable to read gemspec for %s" % build.local_path)

			name = build.name
			version = repr(build.gemspec.version)
			platform = build.gemspec.platform

			id = self.gem_id(build)

			pd = packages.get(name)
			if pd is None:
				pd = {}
				packages[name] = pd

			dupe = pd.get(version)
			if dupe:
				dupe_id = self.gem_id(dupe)
				if id == dupe_id:
					print("%s: two gems with the same platform - randomly picking %s over %s" % (id, dupe.local_path, build.local_path))
					continue

				if platform == 'ruby':
					print("preferring %s over %s" % (dupe_id, id))
					continue

				print("preferring %s over %s" % (id, dupe_id))

			pd[version] = build

		info_path = os.path.join(self.repo_dir, "info")
		if not os.path.isdir(info_path):
			os.makedirs(info_path, mode = 0o755)

		info_hash_algo = 'sha256'
		index_hash_algo = 'md5'

		index = []
		for name in sorted(packages.keys()):
			pd = packages[name]
			versions = []
			info = []

			for version in sorted(pd.keys(), key = ruby_utils.Ruby.ParsedVersion):
				build = pd[version]

				info_line = "%s |" % build.version

				info_line += "checksum:" + self.hash_file(info_hash_algo, build.local_path)

				gemspec = build.gemspec
				if gemspec.required_ruby_version:
					info_line += ",ruby:%s" % gemspec.required_ruby_version
				if gemspec.required_rubygems_version:
					info_line += ",rubygems:%s" % gemspec.required_rubygems_version

				info.append(info_line)

				versions.append(build.version)

			info_file = os.path.join(info_path, name)
			with open(info_file, "w") as f:
				for info_line in info:
					print(info_line, file = f)

			index_line = "%s %s %s" % (
					name,
					",".join(versions),
					self.hash_file(index_hash_algo, info_file))
			index.append(index_line)

		index_path = os.path.join(self.repo_dir, "versions")
		with open(index_path, "w") as f:
			for line in index:
				print(line, file = f)

	def gem_id(self, build):
		platform = build.gemspec.platform
		if platform != 'ruby':
			id = "%s-%s(%s)" % (build.name, build.version, platform)
		else:
			id = "%s-%s" % (build.name, build.version)

		return id

	def hash_file(self, algo, path):
		import hashlib

		m = hashlib.new(algo)
		with open(path, "rb") as f:
			m.update(f.read())

		return m.hexdigest()


class RubyEngine(brcoti_core.Engine):
	type = 'ruby'

	REQUIRED_HASHES = ()

	def __init__(self, config, engine_config):
		super(RubyEngine, self).__init__(config, engine_config)

	def create_index_from_repo(self, repo_config):
		return RubySpecIndex(repo_config.url)

	def create_uploader_from_repo(self, repo_config):
		return RubyUploader(repo_config.url, user = repo_config.user, password = repo_config.password)

	def create_publisher_from_repo(self, repo_config):
		return RubyPublisher(repo_config)

	def create_binary_download_finder(self, req, verbose = False):
		return RubyBinaryDownloadFinder(req, verbose)

	def create_source_download_finder(self, req, verbose = False):
		return RubySourceDownloadFinder(req, verbose)

	# Used by the build-requires parsing
	def create_empty_requirement(self, name):
		return RubyBuildRequirement(name)

	def parse_build_requirement(self, req_string):
		return RubyBuildRequirement.from_string(req_string)

	def prepare_environment(self, compute_backend, build_info):
		return super(RubyEngine, self).prepare_environment(compute_backend, build_info)

	def create_artefact_from_local_file(self, path):
		return RubyArtefact.from_local_file(path)

	def create_artefact_from_NVT(self, name, version, type):
		return RubyArtefact(name, version, type)

	def infer_build_requirements(self, sdist):
		result = []
		if sdist.is_source:
			req = RubyBuildRequirement(sdist.name, "==%s" % sdist.version)
			req = "%s==%s" % (sdist.name, sdist.version)
			build = self.resolve_build_requirement(req)

			if not build.local_path:
				self.downloader.download(build)

			if not build.gemspec:
				build.read_gemspec_from_gem()

			for dep in build.gemspec.dependencies:
				if dep.type != 'development':
					continue

				dep = RubyBuildRequirement(dep.name, dep.format(), dep)
				result.append(dep)

		return result

	def install_requirement(self, compute, req):
		# Sometimes, a package will specify a dependency such as
		#  bundler >= 1.0, < 3
		# It seems that gem install --version is not equipped to deal with this

		assert(req.cooked_requirement)
		gem_req = req.cooked_requirement
		version_string = gem_req.format_versions()

		pkg = self.resolve_build_requirement(req)
		if not pkg:
			raise ValueError("Unable to satisfy dependency %s" % (req.format()))

		version_string = str(pkg.version)
		print("Using %s to satisfy dependency %s" % (pkg.id(), gem_req.format()))

		cmd = ["gem", "install"]
		if version_string:
			cmd += ["--version", "'" + version_string + "'"]

		# Duh, more braindeadness
		cmd.append('--no-format-executable')

		# For some weird reasons, gem seems to ignore all proxy related
		# environment variables and insists that you use a command line
		# option
		proxy = self.config.globals.http_proxy
		if proxy and self.use_proxy:
			cmd += ["--http-proxy", proxy]

		cmd.append(gem_req.name)

		cmd = " ".join(cmd)
		compute.run_command(cmd, privileged_user = True)

	def create_build_strategy_default(self):
		return BuildStrategy_GemBuild()

	def create_build_strategy(self, name, *args):
		if name == 'default':
			return BuildStrategy_GemBuild()
		if name == 'auto':
			return BuildStrategy_Auto()
		if name == 'rake':
			return BuildStrategy_Rake(*args)
		if name == 'bundler':
			return BuildStrategy_Bundler(*args)
		if name == 'gem-build':
			return BuildStrategy_GemBuild(*args)
		if name == 'gem-compile':
			return BuildStrategy_GemCompile(*args)

		super(RubyEngine, self).create_build_strategy(name, *args)

	def build_unpack(self, compute, build_info, auto_repair = False):
		if len(build_info.sources) != 1:
			raise ValueError("Currently unable to handle builds with more than one source")
		sdist = build_info.sources[0]

		bd = RubyBuildDirectory(compute, self)
		if sdist.git_url():
			bd.unpack_git(sdist, sdist.id())
		else:
			bd.unpack_archive(sdist)

		print("Unpacked %s to %s" % (sdist.id(), bd.unpacked_dir()))

		if build_info.patches:
			bd.apply_patches(build_info)

		requirements = bd.infer_build_dependencies()
		missing = []

		for req in requirements:
			try:
				found = self.resolve_build_requirement(req, verbose = False)
			except:
				found = None

			if not found:
				missing.append(req)

		if missing and auto_repair:
			missing = self.merge_from_upstream(missing)

		if missing:
			raise brcoti_core.UnsatisfiedDependencies("Build of %s has unsatisfied dependencies" % sdist.id(), missing)

		return bd

	def merge_from_upstream(self, missing_deps):
		if not self.binary_extra_dir:
			print("Unable to auto-add missing depdencies: binary_extra_dir not set")
			return missing

		still_missing = []
		rebuild_index = False
		for req in missing_deps:
			print("Trying %s" % req)
			finder = self.create_binary_download_finder(req, False)
			found = finder.get_best_match(self.upstream_index)
			if found is None:
				print("No upstream package to satisfy requirement %s" % req)
				print("Requirement %s: no upstream package to satisfy requirement" % req)
				still_missing.append(req)
				continue

			try:
				self.downloader.download(found, destdir = self.binary_extra_dir)
			except:
				print("Requirement %s: download from %s failed" % (req, found.url))
				still_missing.append(req)
				continue

			print("Requirement %s: downloaded from %s" % (req, found.url))
			rebuild_index = True

		if rebuild_index:
			self.publish_build_results()

def engine_factory(config, engine_config):
	return RubyEngine(config, engine_config)
