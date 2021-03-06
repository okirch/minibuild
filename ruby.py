#
# rubygem specific portions of minibuild
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
import minibuild.ruby_utils

import minibuild.core as core

ENGINE_NAME	= 'ruby'
ORIGIN_GEMFILE	= 'bundler'

def get_ruby_version():
	return os.popen("ruby -e 'print(RUBY_VERSION)'").read()

def get_rubygems_version():
	return os.popen("ruby -e 'print(Gem::VERSION)'").read()

def canonical_package_name(name):
	return name

class RubyBuildRequirement(core.BuildRequirement):
	engine = ENGINE_NAME

	def __init__(self, name, req_string = None, cooked_requirement = None):
		super(RubyBuildRequirement, self).__init__(canonical_package_name(name), req_string, cooked_requirement)

		# By default, always require pure ruby
		self.platform = 'ruby'

	def parse_requirement(self, req_string):
		self.cooked_requirement = minibuild.ruby_utils.Ruby.parse_dependency(req_string)
		self.req_string = req_string

	@staticmethod
	def from_string(req_string):
		cooked_requirement = minibuild.ruby_utils.Ruby.parse_dependency(req_string)
		return RubyBuildRequirement(cooked_requirement.name, req_string, cooked_requirement)

	@staticmethod
	def from_cooked(gem_dependency):
		return RubyBuildRequirement(gem_dependency.name, gem_dependency.format(), gem_dependency)

	def merge(self, other):
		assert(isinstance(other, RubyBuildRequirement))
		assert(self.name == other.name)
		assert(self.cooked_requirement)
		assert(other.cooked_requirement)

		# Both cooked_requirement are a Gem::Dependency
		merge = RubyBuildRequirement(self.name)

		merge.cooked_requirement = self.cooked_requirement.merge(other.cooked_requirement)

		if self.origin_priority() < other.origin_priority():
			merge.origin = other.origin
		else:
			merge.origin = self.origin

		# print("merged: %s + %s => %s" % (self, other, merge))
		return merge

	origin_order = (
			'package',
			ORIGIN_GEMFILE,
			'spec',
			'commandline'
		)
	def origin_priority(self):
		if self.origin in self.origin_order:
			return self.origin_order.index(self.origin)
		return -1

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

	def valid_platform(self):
		return self.cooked_requirement.valid_platform()

class RubyArtefact(core.Artefact):
	engine = ENGINE_NAME

	def __init__(self, name, version = None, type = None):
		super(RubyArtefact, self).__init__(canonical_package_name(name), version)

		self.type = type
		self.platform = 'ruby'
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

	def id(self):
		r = super(RubyArtefact, self).id()
		if self.platform and self.platform != 'ruby':
			r += "-" + self.platform
		return r

	def verify_minimum_version(self, my_version, req_version):
		if req_version is None:
			return True

		# print("verify_minimum_version(mine=%s, wanted=%s)" % (my_version, req_version))
		return my_version in req_version

	def verify_required_ruby_version(self):
		return self.verify_minimum_version(get_ruby_version(), self.required_ruby_version)

	def verify_required_rubygems_version(self):
		return self.verify_minimum_version(get_rubygems_version(), self.required_rubygems_version)

	def get_install_requirements(self):
		if not self.gemspec:
			if not self.local_path:
				return []
			self.read_gemspec_from_gem()
			assert(self.gemspec)

		result = []
		for dep in self.gemspec.dependencies:
			if dep.type not in ('development', ):
				result.append(RubyBuildRequirement.from_cooked(dep))

		return result

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

		# FIXME: rather than all the funky parsing stuff, we should
		# probably parse the gem spec and be done with
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

		try:
			self._set_gemspec(GemFile(self.local_path).parse_metadata())
		except Exception as e:
			print("Unable to read gemspec from %s - parse error" % self.local_path)
			raise e

	def _set_gemspec(self, gemspec):
		self.gemspec = gemspec

		self.name = gemspec.name
		self.version = str(gemspec.version)

		# Sometimes, the platform is just a string, sometimes it's a Gem::Platform
		# instance. We don't care, we force it to string.
		if gemspec.platform:
			self.platform = str(gemspec.platform)

		if self.filename is None:
			if self.platform and self.platform != 'ruby':
				self.filename = "%s-%s-%s.gem" % (self.name, self.version, self.platform)
			else:
				self.filename = "%s-%s.gem" % (self.name, self.version)

		self.author = gemspec.author
		self.homepage = gemspec.homepage

		self.required_ruby_version = gemspec.required_ruby_version
		self.required_rubygems_version = gemspec.required_rubygems_version

class RubyReleaseInfo(core.PackageReleaseInfo):
	def __init__(self, name, version, platform = 'ruby', parsed_version = None):
		super(RubyReleaseInfo, self).__init__(canonical_package_name(name), version)
		self.platform = platform

		if not parsed_version:
			parsed_version = minibuild.ruby_utils.Ruby.ParsedVersion(version)

		self.parsed_version = parsed_version

	def id(self):
		if self.platform != 'ruby':
			return "%s-%s-%s" % (self.name, self.version, self.platform)
		return "%s-%s" % (self.name, self.version)

	def more_recent_than(self, other):
		assert(isinstance(other, RubyReleaseInfo))
		return other.parsed_version < this.parsed_version

class RubyPackageInfo(core.PackageInfo):
	def __init__(self, name):
		super(RubyPackageInfo, self).__init__(canonical_package_name(name))

class RubyDownloadFinder(core.DownloadFinder):
	def __init__(self, req, verbose, cooked_requirement = None):
		super(RubyDownloadFinder, self).__init__(verbose)

		if type(req) != RubyBuildRequirement:
			req = RubyBuildRequirement.from_string(req)

		self.requirement = req.cooked_requirement
		self.name = req.name
		self.allow_prereleases = False
		self.platform = req.platform

		if self.verbose:
			print("Looking for %s; platform=%s" % (req, req.platform))

	def release_match(self, release):
		assert(release.parsed_version)
		if not self.allow_prereleases and release.parsed_version.is_prerelease:
			return False

		if self.platform and self.platform != release.platform:
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

		good_match = None
		best_match = None
		best_release = None

		releases = sorted(info.releases, key = lambda r: r.parsed_version)
		while releases and not best_match:
			best_release = releases.pop()

			if not self.release_match(best_release):
				if self.verbose:
					print("ignoring release %s" % best_release.id())
				continue

			if self.verbose:
				print("inspecting release %s" % best_release.id())

			# Create an artefact for the binary gem (by downloading the gemspec
			# from the index).
			# If possible, also create a source artefact by guessing the source
			# URL.
			# The binary artefact will be attached to the cache representing this
			# index; the source artefact will not be attached to any cache.
			index.get_gemspec(best_release, verbose = self.verbose)

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
			print("inspecting %s (type %s, platform %s)" % (build.filename, build.type, build.platform))
			print("  git repo %s" % build.git_repo_url)

		return build.type == 'source'

class RubyBinaryDownloadFinder(RubyDownloadFinder):
	def __init__(self, req, verbose = False, cooked_requirement = None):
		super(RubyBinaryDownloadFinder, self).__init__(req, verbose, cooked_requirement)

	def build_match(self, build):
		if self.verbose:
			print("inspecting %s (type %s, platform %s)" % (build.filename, build.type, build.platform))

		if self.platform and build.platform != self.platform:
			# print("RubyBinaryDownloadFinder: build platform %s doesn't match requested platform %s" % (build.platform, self.platform))
			return False

		return build.type == 'gem'

class RubySpecIndex(core.HTTPPackageIndex):
	def __init__(self, url):
		super(RubySpecIndex, self).__init__(url)

		# For some bizarre reason, the specs files are avaliable from nexus in different compression
		# formats, but the gemspec is only provided as zlib compressed file
		self._pkg_url_template = "{index_url}/quick/Marshal.4.8/{pkg_name}-{pkg_version}.gemspec.rz"

		self.zap_cache()

	def zap_cache(self):
		super(RubySpecIndex, self).zap_cache()

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
				if isinstance(version_list, minibuild.ruby_utils.Ruby.GemVersion):
					version = str(version_list)
				else:
					version = version_list[0]

				platform = gem[2]

				release = RubyReleaseInfo(name, version, platform)
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

		from minibuild.ruby_utils import unmarshal

		# This is fairly slow... need to speed this up!
		return unmarshal(filename, resp)

	def get_gemspec(self, release, verbose = False):
		import urllib.request

		version = release.version
		platform = release.platform
		if platform and platform != 'ruby':
			version = "%s-%s" % (release.version, platform)

		url = self._pkg_url_template.format(index_url = self.url, pkg_name = release.name, pkg_version = version)

		if verbose:
			print("Getting gemspec for %s-%s-%s from %s" % (release.name, release.version, platform, url))

		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to get package info for %s-%s: HTTP response %s (%s)" % (
					release.name, version, resp.status, resp.reason))

		self.process_gemspec_response(resp, release)

	def process_gemspec_response(self, resp, release):
		from minibuild.ruby_utils import unmarshal

		gemspec = unmarshal(resp.url, resp)

		release.add_build(self.gemspec_to_binary(gemspec))

		build = self.gemspec_to_source(gemspec)
		if build:
			release.add_build(build)

	def gemspec_to_binary(self, gemspec):
		build = self.gemspec_to_build_common(gemspec, 'gem')

		build.url = "%s/gems/%s" % (self.url, build.filename)
		build.cache = self.cache
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

		# This sets platform, filename, author, homepage, required_*_versions
		build._set_gemspec(gemspec)

		build.url = "%s/gems/%s" % (self.url, build.filename)

		if False:
			for attr_name in dir(gemspec):
				attr_val = getattr(gemspec, attr_name)
				if callable(attr_val) or attr_name.startswith('_'):
					continue
				print("%-20s = %s" % (attr_name, attr_val))

			for key, value in gemspec.metadata.items():
				print("metadata." + key, value)

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
class RubyUploader(core.Uploader):
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
		core.run_command("gem nexus %s" % build.local_path)

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
	# has_rdoc is deprecated, and "gem build" does not set it
	metadata_badness = {
		'date' : 0,
		'rubygems_version' : 0,
		'specification_version' : 0,
		'cert_chain' : 0,
		'has_rdoc' : 0,
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

		result = core.ArtefactComparison(new.path)

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
		return minibuild.ruby_utils.Ruby.YAML.load(io)

class RubyBuildStrategy(core.BuildStrategy):
	pass

class NestedRubyBuildStrategy(RubyBuildStrategy):
	def __init__(self, inner_job):
		self.inner_job = inner_job

	def describe(self):
		return '%s(%s)' % (self._type, self.inner_job.describe())

	def implicit_build_dependencies(self, build_directory):
		return self.inner_job.implicit_build_dependencies(build_directory)

	def resolve_source(self, source):
		super(NestedRubyBuildStrategy, self).resolve_source(source)
		self.inner_job.resolve_source(source)

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
			built_some = False
			for spec in build_directory.directory.glob_files("*.gemspec"):
				yield "gem build '%s'" % os.path.basename(spec.path)
				built_some = True

			if not built_some:
				raise ValueError("No gemspec files in build directory %s" % build_directory.directory)

class BuildStrategy_GemCompile(NestedRubyBuildStrategy):
	_type = "gem-compile"
	_requires = ['gem-compiler']

	def __init__(self, inner_job, name = None):
		super(BuildStrategy_GemCompile, self).__init__(inner_job)
		self.inner_job_done = False
		self.name = name

	def describe(self):
		if self.name:
			return '%s(%s, %s)' % (self._type, self.inner_job.describe(), self.name)
		else:
			return '%s(%s)' % (self._type, self.inner_job.describe())

	def next_command(self, build_directory):
		# This self.inner_job_done thingy allows BuildStrategy_Auto to create
		# a GemCompile strategy without re-running the inner job
		if not self.inner_job_done:
			for cmd in self.inner_job.next_command(build_directory):
				yield cmd
			self.inner_job_done = True

		if self.name:
			yield "gem compile '%s'-*.gem" % self.name
		else:
			for spec in build_directory.glob_build_results(paths_only = True):
				yield "gem compile '%s'" % spec.path

	def build_dependencies(self, build_directory):
		return self._build_dependencies(build_directory, nested_strategy = self.inner_job)

	def build_used(self, build_directory):
		return self.inner_job.build_used(build_directory)

class BuildStrategy_Rake(RubyBuildStrategy):
	_type = "rake"
	_requires = ['rake']

	def __init__(self, *targets):
		super(BuildStrategy_Rake, self).__init__()
		if not targets:
			targets = ['build']
		self.targets = targets

	def describe(self):
		return '%s(%s)' % (self._type, ", ".join(self.targets))

	def next_command(self, build_directory):
		# FIXME: should we try to detect supported rake tasks
		# if none were given?
		for tgt in self.targets:
			yield "rake %s" % tgt

class BuildStrategy_Thor(RubyBuildStrategy):
	_type = "thor"
	_requires = ['thor']

	def __init__(self, *targets):
		super(BuildStrategy_Thor, self).__init__()
		if not targets:
			targets = ['build']
		self.targets = targets

	def describe(self):
		return '%s(%s)' % (self._type, ", ".join(self.targets))

	def next_command(self, build_directory):
		# FIXME: should we try to detect supported rake tasks
		# if none were given?
		for tgt in self.targets:
			yield "thor %s" % tgt

class BuildStrategy_Bundler(NestedRubyBuildStrategy):
	_type = "bundler"
	_requires = ['bundler']

	def __init__(self, inner_job):
		super(BuildStrategy_Bundler, self).__init__(inner_job)
		self.locked_bundler_version = None
		self.gemfile_parsed = None
		self.gemfile_lock_parsed = None
		self.config = []

	def apply_config(self, value):
		self.config.append(value)

	def next_command(self, build_directory):
		# While we bootstrap ruby building, skip everything test related and go just for the build
		yield "bundle config bindir '%s'" % "/home/build/bin"
		yield "bundle config path '%s'" % "/home/build/.gem"

		for value in self.config:
			yield "bundle config " + value

		# While we bootstrap ruby building, skip everything test related and go just for the build
		yield "bundle config without test benchmark"

		cmd = "bundler install"
		if False:
			cmd += " --full-index"
		yield cmd

		for cmd in self.inner_job.next_command(build_directory):
			yield "bundler exec " + cmd

	def build_dependencies(self, build_directory):
		result = []
		if self.locked_bundler_version:
			print("Gemfile.lock specifies bundler == %s" % self.locked_bundler_version)
			result = ['bundler == %s' % self.locked_bundler_version]
		elif not build_directory.has_build_dependency('bundler'):
			print("Not locked to a specific version of bundler")
			result.append('bundler')
		return result + self.inner_job.build_dependencies(build_directory)

	def build_used(self, build_directory):
		result = self.inner_job.build_used(build_directory)

		gems = build_directory.inspect_gem_cache(build_directory.bundler_cache_dir)
		gems += build_directory.inspect_gem_cache(build_directory.rubygem_user_cache_dir)

		for w in gems:
			build = RubyArtefact.from_local_file(w.hostpath())
			for algo in RubyEngine.REQUIRED_HASHES:
				build.update_hash(algo)
			result.append(build)

		return result

	# TBD: run bundle package to collect the used gems into vendor/cache
	# and return them for inclusion in the build-info file

	def implicit_build_dependencies(self, build_directory):
		directory = build_directory.directory
		req_set = core.RequirementSet()

		req_set.add_list(self.gemfile_requirements(directory))
		req_set.add_list(self.gemfile_lock_requirements(directory))
		req_set.add_list(self.inner_job.implicit_build_dependencies(build_directory))

		req_set.show("Bundler requirements")
		return req_set.all()

	def gemfile_requirements(self, directory):
		import bundler

		if self.gemfile_parsed is not None:
			return self.gemfile_parsed

		file = directory.lookup('Gemfile')
		if file is None:
			return []

		# FIXME: we need a global RUBY_VERSION config item
		ctx = bundler.Context("2.5.0")
		ctx.with_group("development")

		try:
			gemfile = bundler.Gemfile(file.hostpath(), ctx)
		except Exception as e:
			print("Failed to parse Gemfile")
			print(e)
			return []

		result = []
		for r in gemfile.required():
			if 'source=' in r:
				i = r.index('source=')
				source = r[i+7:]
				r = r[:i]
			else:
				source = None

			req = RubyBuildRequirement.from_string(r)
			req.origin = ORIGIN_GEMFILE
			req.index_url = source

			if not req.valid_platform():
				print("Ignoring Gemfile requirement %s" % req)
				continue

			result.append(req)

		self.gemfile_parsed = result
		return result

	def gemfile_lock_requirements(self, directory):
		if self.gemfile_lock_parsed is not None:
			return self.gemfile_lock_parsed

		result = []

		loc = directory.lookup('Gemfile.lock')
		if loc is not None:
			gemfile_lock = minibuild.ruby_utils.Ruby.GemfileLock.parse(loc)

			print("Analyzing contents of Gemfile.lock")
			# gemfile_lock.dump()

			# gemfile_lock.requirements() returns a list of
			# GemDependency objects; we need to convert these into
			# RubyBuildRequirements
			for dep in gemfile_lock.requirements():
				req = RubyBuildRequirement.from_cooked(dep)
				req.origin = ORIGIN_GEMFILE

				if not req.valid_platform():
					print("Ignoring Gemfile.lock requirement %s" % req)
					continue

				result.append(req)

			self.locked_bundler_version = gemfile_lock.bundler_version()
			if self.locked_bundler_version:
				print("Locked to bundler version %s" % self.locked_bundler_version)

		self.gemfile_lock_parsed = result
		return result

class BuildStrategy_Auto(RubyBuildStrategy):
	_type = "auto"

	def __init__(self):
		self.actual = None

	def describe(self):
		if self.actual:
			return self.actual.describe()
		return "auto"

	def actual_strategy(self, build_directory, want_compiler = False):
		where = build_directory.directory

		strategy = None

		rakefile = where.lookup("Rakefile")
		thorfile = where.lookup("Thorfile")
		if rakefile is not None:
			using_hoe = False
			with rakefile.open() as f:
				for l in f.readlines():
					if "Hoe.spec" in l:
						using_hoe = True

			if using_hoe:
				targets = ('gem', )
			else:
				targets = ('build', )

			strategy = BuildStrategy_Rake(*targets)
		elif thorfile is not None:
			strategy = BuildStrategy_Thor()

		# If we have neither Rakefile nor Thorfile, fall back to
		# a simple "gem build"
		if strategy is None:
			strategy = BuildStrategy_GemBuild()

		if where.lookup("Gemfile"):
			strategy = BuildStrategy_Bundler(strategy)

		if want_compiler:
			strategy = BuildStrategy_GemCompile(strategy)

		return strategy

	def next_command(self, build_directory):
		strategy = self.actual_strategy(build_directory)

		for cmd in strategy.next_command(build_directory):
			yield cmd

		# TODO: now look at the results and see if they contain
		# a native extension. If so, compile than gem (and alter
		# our strategy)
		need_compile = False
		print("Checking build results for extensions")
		for artefact in build_directory.glob_build_results():
			print("%s %s" % (artefact.id(), artefact.gemspec.extensions))
			if artefact.gemspec.extensions:
				print("Gem %s has extensions; should be compiled" % artefact.id())
				need_compile = True

		if need_compile:
			strategy = BuildStrategy_GemCompile(strategy)

			# Do not re-run bundler/rake/gem build
			strategy.inner_job_done = True

			for cmd in strategy.next_command(build_directory):
				yield cmd

		self.actual = strategy

	# This returns a list of requirements specified by the package build
	# files like Gemfile/Gemfile.lock
	def implicit_build_dependencies(self, build_directory):
		strategy = self.actual
		if strategy is None:
			strategy = self.actual_strategy(build_directory, want_compiler = True)
		return strategy.implicit_build_dependencies(build_directory)

	# We're called twice. Once _before_ the build run, and once _after_.
	# In the call before, we should always include gem-compiler to make sure it
	# gets installed.
	# In the call after, we should only include gem-compiler if the gem has
	# and extension that needed compiling.
	def build_dependencies(self, build_directory):
		strategy = self.actual
		if strategy is None:
			strategy = self.actual_strategy(build_directory, want_compiler = True)
		return strategy.build_dependencies(build_directory)

	def build_used(self, build_directory):
		return self.actual.build_used(build_directory)

class RubyBuildDirectory(core.BuildDirectory):
	def __init__(self, compute, engine):
		super(RubyBuildDirectory, self).__init__(compute, engine)

		gem_cache_path = engine.engine_config.get_value("gem-system-cache")
		if not gem_cache_path:
			raise ValueError("Configuration does not specify gem-system-cache")

		self.rubygem_system_cache_dir = compute.get_directory(gem_cache_path)
		if not self.rubygem_system_cache_dir:
			raise ValueError("Configuration specifies gem-system-cache \"%s\", which does not exist in the compute environment" % gem_cache_path)

		self.rubygem_user_cache_dir = engine.engine_config.get_value("gem-user-cache")
		if not self.rubygem_user_cache_dir:
			raise ValueError("Configuration does not specify gem-user-cache")

		# bundler-cache is a relative path, which only makes sense within the build
		# directory, and only once we've run bundler install
		self.bundler_cache_dir = engine.engine_config.get_value("bundler-cache")
		if not self.bundler_cache_dir:
			raise ValueError("Configuration does not specify bundler-cache")

		self.pre_build_gems = self.get_installed_gems()

	# Most of the unpacking happens in the BuildDirectory base class.
	# The only python specific piece is guessing which directory an archive is extracted to
	def archive_get_unpack_directory(self, sdist):
		name, version, type = RubyArtefact.parse_filename(sdist.filename)
		return name + "-" + version

	def glob_build_results(self, paths_only = False):
		gems = self.directory.glob_files("*.gem")

		pkgdir = self.directory.lookup("pkg")
		if pkgdir is not None:
			gems += pkgdir.glob_files("*.gem")

		if paths_only:
			return gems

		result = []
		for w in gems:
			build = RubyArtefact.from_local_file(w.hostpath())
			build.read_gemspec_from_gem()
			result.append(build)

		return result

	def collect_build_results(self):
		build_results = self.glob_build_results()

		print("Successfully built %s: %s" % (self.sdist.id(), ", ".join([a.filename for a in build_results])))
		for artefact in build_results:
			for algo in RubyEngine.REQUIRED_HASHES:
				build.update_hash(algo)

		self.build_info.artefacts = build_results
		return build_results

	# Compare old build of a gem vs the current build. This method
	# is expected to return an ArtefactComparison object
	def compare_build_artefacts(self, old_path, new_path):
		return GemFile(old_path).compare(GemFile(new_path))

	# It would be better if we'd inspect the build log for the actual artefacts
	# used, rather than going through the spec index ourselves. However, for the
	# time being I don't know where to actually get this info from
	#
	# FIXME: if we have a Gemfile but no Gemfile.lock, we might ay well run
	# "bundler lock" inside the container to get a nice and clean list of
	# dependencies
	def guess_build_dependencies(self, build_strategy = None):
		from packaging.requirements import Requirement

		seen = dict()
		for build in self.build_info.artefacts + [self.sdist, ]:
			if not build.gemspec:
				if not build.is_source:
					print("Warning: no gemspec info for %s" % build.filename)
				continue

			self.add_build_dependencies_from_gemspec(build.gemspec, seen)

		if build_strategy:
			for req_string in build_strategy.build_dependencies(self):
				req = RubyBuildRequirement.from_string(req_string)
				self.build_info.requires.append(req)

		self.post_build_gems = self.get_installed_gems()

		changes = self.pre_build_gems.changes(self.post_build_gems)
		if changes:
			gem_list = self.inspect_gem_cache(self.bundler_cache_dir) + \
				   self.inspect_gem_cache(self.rubygem_user_cache_dir)

			gem_dict = { os.path.basename(gem.path) : gem for gem in gem_list }

			# Should we record all gems found in this directory,
			# or just the ones that were added since startup
			# of the container?
			for id in changes.added:
				cached_gem = gem_dict.get("%s.gem" % id)
				if cached_gem is None:
					print("WARNING: Gem %s was installed, but could not find it in cache" % id)
					continue

				artefact = RubyArtefact.from_local_file(cached_gem.hostpath())

				for algo in RubyEngine.REQUIRED_HASHES:
					artefact.update_hash(algo)
				self.build_info.used.append(artefact)

		if build_strategy:
			self.build_info.used += build_strategy.build_used(self)
			# self.compute.run_command("find", working_dir = self.directory)

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

	def get_installed_gems(self):
		with self.compute.popen("gem list") as f:
			return minibuild.ruby_utils.Ruby.GemList.parse(f)

	def inspect_gem_cache(self, cache_dir):
		if not isinstance(cache_dir, core.ComputeResourceDirectory):
			compute = self.compute

			# This code should be in the ComputeNode class
			if cache_dir.startswith('/'):
				cache_dir = compute.get_directory(cache_dir)
			elif cache_dir.startswith('~/'):
				cache_path = os.path.join(compute.build_home, cache_dir[2:])
				cache_dir = compute.get_directory(cache_path)
			else:
				cache_dir = self.directory.lookup(cache_dir)

			if cache_dir is None:
				return []

		print("Looking for downloaded gems in %s" % cache_dir.path)
		return cache_dir.glob_files("*.gem")

class RubyPublisher(core.Publisher):
	def __init__(self, repoconfig):
		super(RubyPublisher, self).__init__("ruby", repoconfig)

		self.gems = set()

	def prepare(self):
		self.prepare_repo_dir()
		self.gems_dir = self.prepare_repo_subdir("gems")
		self.gems = set()

		self.processor = None

	def is_artefact(self, path):
		return path.endswith(".gem")

	def publish_artefact(self, path):
		gem_name = os.path.basename(path)
		if self.processor:
			path = self.processor(path)

		shutil.copy(path, self.gems_dir)

		path = os.path.join(self.gems_dir, os.path.basename(path))
		self.gems.add(path)

	def finish(self):
		cmd = "gem generate_index --directory %s" % self.repo_dir
		core.run_command(cmd)

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

			if platform != 'ruby':
				version += "-" + platform

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

			for version in sorted(pd.keys(), key = minibuild.ruby_utils.Ruby.ParsedVersion):
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


class RubyEngine(core.Engine):
	type = 'ruby'

	REQUIRED_HASHES = ()

	def __init__(self, engine_config):
		super(RubyEngine, self).__init__(engine_config)

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

	def prepare_environment(self, compute_backend, build_spec):
		compute = super(RubyEngine, self).prepare_environment(compute_backend, build_spec)

		# Make sure that commands we execute as user build find gem binaries in ~/bin
		self.add_bindir_to_user_path(compute, compute.build_home)

		return compute

	def add_bindir_to_user_path(self, compute, homedir):
		home = compute.get_directory(homedir)
		if home is None:
			print("WARNING: Can't find %s, unable to add ~/bin to path" % homedir)
			return

		bindir = home.lookup("bin")
		if bindir is None:
			home.mkdir("bin")

		bashrc = home.lookup(".bashrc")
		if bashrc is not None:
			with bashrc.open("r") as f:
				for l in f.readlines():
					if "@@minibuild path@@" in l:
						print("%s already sets PATH to include ~/bin" % bashrc.path)
						return

		with bashrc.open("a") as f:
			print("# Do not remove this: @@minibuild path@@", file = f)
			print("PATH=~/bin:$PATH", file = f)

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
				dep.origin = "package"
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

		cmd.append('--no-document')
		cmd.append('--user-install')

		cmd += ['--bindir', compute.build_home + "/bin"]

		# For some weird reasons, gem seems to ignore all proxy related
		# environment variables and insists that you use a command line
		# option
		proxy = self.config.globals.http_proxy
		if proxy and self.use_proxy:
			cmd += ["--http-proxy", proxy]

		cmd.append(gem_req.name)

		cmd = " ".join(cmd)
		# compute.run_command(cmd, privileged_user = True)
		compute.run_command(cmd)

		return pkg

	def create_build_strategy_default(self):
		return BuildStrategy_GemBuild()

	def create_build_strategy(self, name, *args):
		if name == 'default':
			return BuildStrategy_GemBuild()
		if name == 'auto':
			return BuildStrategy_Auto()
		if name == 'rake':
			return BuildStrategy_Rake(*args)
		if name == 'thor':
			return BuildStrategy_Thor(*args)
		if name == 'bundler':
			return BuildStrategy_Bundler(*args)
		if name == 'gem-build':
			return BuildStrategy_GemBuild(*args)
		if name == 'gem-compile':
			return BuildStrategy_GemCompile(*args)

		return super(RubyEngine, self).create_build_strategy(name, *args)

	def create_build_directory(self, compute):
		return RubyBuildDirectory(compute, self)

	def merge_from_upstream(self, missing_deps, requirements = None, update_index = True):
		if not self.binary_extra_dir:
			print("Unable to auto-add missing depdencies: binary_extra_dir not set")
			return missing

		still_missing = []
		added = False
		for req in list(missing_deps):
			print("Trying %s" % req)
			finder = self.create_binary_download_finder(req, False)

			try:
				found = finder.get_best_match(self.upstream_index)
			except:
				found = None
			if found is None:
				print("No upstream package to satisfy requirement %s" % req)
				print("Requirement %s: no upstream package to satisfy requirement" % req)
				still_missing.append(req)
				continue

			try:
				found_path = self.downloader.download(found)
			except:
				print("Requirement %s: download from %s failed" % (req, found.url))
				still_missing.append(req)
				continue

			print("Requirement %s: downloaded from %s" % (req, found.url))
			shutil.copy(found_path, self.binary_extra_dir)
			added = True

			if type(missing_deps) == set:
				missing_deps.remove(req)

			if requirements is not None:
				requirements.update(self.resolve_install_requirements(found))

		if added and update_index:
			self.publish_build_results()


		return still_missing

	# This is for the comparison of the artefacts we built with upstream
	def get_upstream_build_for(self, sdist, artefact):
		req_string = "%s == %s" % (sdist.name, sdist.version)

		print("Trying to find upstream build for %s, platform=%s" % (req_string, artefact.platform))
		req = self.parse_build_requirement(req_string)

		# Do not compare compiled artefacts with their upstream
		# (pure ruby) build.
		if artefact.platform == 'x86_64-linux':
			return None

		if artefact.platform != 'ruby':
			req.platform = artefact.platform

		finder = self.create_binary_download_finder(req, verbose = False)
		upstream = finder.get_best_match(self.upstream_index)
		if not upstream:
			raise ValueError("No upstream build for %s" % req_string)

		print("Found build %s" % upstream.id())
		print("  platform=%s" % upstream.platform)
		return upstream

def engine_factory(engine_config):
	return RubyEngine(engine_config)
