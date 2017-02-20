from __future__ import print_function
from __future__ import absolute_import
from builtins import next
from builtins import str
from builtins import object
import os, os.path, shutil, subprocess, re, sys, glob, tempfile, contextlib, fnmatch
from collections import OrderedDict, namedtuple
from .version_maker import eups_to_conda_version
from .utils import fill_out_template, create_yaml_list
import json
import yaml

ProductInfo = namedtuple('ProductInfo', ['conda_name', 'version', 'build_string', 'buildnum', 'product', 'eups_version', 'is_built', 'is_ours'])

class RecipeMaker(object):
    def __init__(self, config, root_dir, db):
        self.config = config
        self.root_dir = root_dir
        self.db = db

        self.products = OrderedDict()   # A mapping from conda_name -> ProductInfo instance

    def report_progress(self, product, verstr = None):
        if verstr is not None:
            print("  %s-%s...  " % (product, verstr))
        else:
            print("  %s...  " % product)
        sys.stdout.flush()

    def conda_version_spec(self, conda_name):
        pi = self.products[conda_name]
        if pi.version is not None:
            verexpr = ("==" if pi.is_ours else ">=") + pi.version
            return "%s %s" % (conda_name, verexpr)
        else:
            return conda_name

    def prepare_patches(self, product, dir):
        patch_dir = os.path.join(self.config.patch_dir, product)
        if not os.path.isdir(patch_dir):
            return ''

        patch_files = glob.glob(os.path.join(patch_dir, '*.patch'))

        for patchfn in patch_files:
            shutil.copy2(patchfn, dir)

        # convert to meta.yaml string
        patchlist = [ os.path.basename(p) for p in patch_files ]
        patches = '  patches:' + create_yaml_list(patchlist)
        return patches

    def etc_recipe_match(self, conda_name, sha, conda_version):
        """
        Given the conda_name, sha and conda_version return True
        if a matching Conda recipe exists in etc/recipes otherwise
        return False.
        """
        def _check_version(meta):
            if meta.get("package") and meta["package"].get("version"):
                return meta["package"]["version"] == conda_version
        def _check_sha(meta):
            if meta.get("source") and meta["source"].get("git_rev"):
                return meta["source"]["git_rev"] == sha
        meta_path = os.path.join(self.config.additional_recipes_dir,
                                 conda_name,
                                 "meta.yaml")
        if os.path.isfile(meta_path):
            with open(meta_path) as m:
                meta = yaml.load(m)
            return _check_sha(meta) and _check_version(meta)
        return False

    def gen_conda_package(self, product, sha, eups_version, giturl, eups_deps):
        # What do we call this product in conda?
        conda_name = self.config.conda_name_for(product)

        # convert to conda version
        version, build_string_prefix, buildnum, compliant = eups_to_conda_version(product, eups_version, giturl)

        # warn if the version is not compliant
        problem = "" if compliant else " [WARNING: version format incompatible with conda]"

        # write out a progress message
        self.report_progress(conda_name, "%s%s" % (version, problem))

        #
        # process dependencies
        #
        eups_deps = set(eups_deps)
        eups_deps -= self.config.skip_products # skip unwanted dependencies

        # Now start tracking runtime vs build depencendies separately
        # FIXME: We should do this from the start, but EUPS still isn't tracking the two separately
        bdeps, rdeps = [], []
        for prod in eups_deps:
            # Add the dependency
            dep_conda_name = self.config.conda_name_for(prod)
            bdeps.append(dep_conda_name)
            rdeps.append(dep_conda_name)

            # If the dependency is an internal product, add the internal product
            # to the build dependencies as well. This works around the problem where
            # e.g., lsst-afw depends on lsst-numpy-eups-config which depends on
            # numpy ==1.9 in the build section, but numpy >=1.9 in the run. If lsst-afw
            # didn't depend on numpy ==1.9 directly in its build section, then numpy
            # would've been pulled in via lsst-numpy-eups-config's *run* section (and
            # thus may be built against a newer numpy).
            if prod in self.config.internal_products:
                bdeps.append(self.config.internal_products[prod]['build'])

        # If this is an internal product, also add the conda package as a dependency
        try:
            internals = self.config.internal_products[product]
        except KeyError:
            pass
        else:
            bdeps.append(internals['build'])
            rdeps.append(internals['run'])

        bplus, rplus = self.add_missing_deps(conda_name)  # manually add any missing dependencies
        bdeps += bplus
        rdeps += rplus
        bdeps, rdeps = sorted(bdeps), sorted(rdeps)  # sort, so the ordering is predicatble in meta.yaml

        #
        # Create the Conda packaging spec files
        #
        if self.config.prefer_etc_recipes \
           and self.etc_recipe_match(conda_name, sha, version):
            src_dir = os.path.join(self.config.root_dir,
                                   self.config.additional_recipes_dir,
                                   conda_name)
            dest_dir = os.path.join(self.config.output_dir, conda_name)
            src_dir
            if not os.path.isdir(dest_dir):
                shutil.copytree(src_dir, dest_dir)
            dir_ = os.path.join(self.config.output_dir, conda_name)
            buildnum, build_string, is_built = self.get_build_info(conda_name.lower(), version, dir_, build_string_prefix)
        else:
            dir_ = os.path.join(self.config.output_dir, conda_name)
            os.makedirs(dir_)

            # Copy any patches into the recipe dir
            patches = self.prepare_patches(product, dir_)

            # build.sh (TBD: use exact eups versions, instead of -r .)
            setups = []
            SEP = 'setup '
            setups = SEP + ('\n'+SEP).join(setups) if setups else ''

            template_dir = self.config.template_dir

            build_template = 'build.sh.template' if product not in self.config.internal_products else 'build-internal.sh.template'
            fill_out_template(os.path.join(dir_, 'build.sh'),
                              os.path.join(template_dir, build_template),
                              setups = setups,
                              eups_version = eups_version,
                              eups_tags = ' '.join(self.config.global_eups_tags))

            # pre-link.sh (to add the global tags)
            fill_out_template(os.path.join(dir_, 'pre-link.sh'),
                              os.path.join(template_dir, 'pre-link.sh.template'),
                              product = product,)

            # meta.yaml
            rdeps = [ self.conda_version_spec(p) if p in self.products else p for p in rdeps ]
            bdeps = [ self.conda_version_spec(p) if p in self.products else p for p in bdeps ]
            reqstr_r = create_yaml_list(rdeps)
            reqstr_b = create_yaml_list(bdeps)

            meta_yaml = os.path.join(dir_, 'meta.yaml')
            fill_out_template(meta_yaml, os.path.join(template_dir, 'meta.yaml.template'),
                              productNameLowercase = conda_name.lower(),
                              version = version,
                              gitrev = sha,
                              giturl = giturl,
                              build_req = reqstr_b,
                              run_req = reqstr_r,
                              patches = patches,)

            # The recipe is now (almost) complete.
            # Find our build number. If this package already exists in the release DB,
            # re-use the build number and mark it as '.done' so it doesn't get rebuilt.
            # Otherwise, increment the max build number by one and use that.
            buildnum, build_string, is_built = self.get_build_info(conda_name.lower(), version, dir_, build_string_prefix)

            # Fill in the build number and string
            fill_out_template(meta_yaml, meta_yaml,
                              buildnum = buildnum,
                              build_string = build_string)

        # record we've seen this product
        self.products[conda_name] = ProductInfo(
                conda_name, version, build_string,
                buildnum, product, eups_version, is_built, True)


    def get_build_info(self, conda_name, version, recipe_dir, build_string_prefix):
        is_built = False
        hash = self.db.hash_recipe(recipe_dir)
        try:
            buildnum = self.db[conda_name, version, hash]
            is_built = True
        except KeyError:
            buildnum = self.db.get_next_buildnum(conda_name, version)

        build_string = '%s_%s' % (build_string_prefix, buildnum) if build_string_prefix else str(buildnum)

        return buildnum, build_string, is_built

    ##################################
    # Use static recipes to satisfy dependencies
    #
    def copy_additional_recipe(self, name):
        additional_recipes_dir = self.config.additional_recipes_dir
        recipes = os.listdir(additional_recipes_dir)

        def _have_recipe(name):
            return next((dir for dir in recipes if dir == name), None)

        # Now recursively copy the recipe, and all others it depends on
        def _copy_recipe(name):
            src = os.path.join(additional_recipes_dir, name)
            dest = os.path.join(self.config.output_dir, name)
            if os.path.isdir(dest):
                # Already copied
                return

            # copy the additional recipe
            shutil.copytree(src, dest)

            # copy all its dependencies for which we have the recipes
            import yaml
            meta = yaml.load(open(os.path.join(src, 'meta.yaml')))
            for kind in ['run', 'build']:
                if kind in meta.get('requirements', {}):
                    for dep in meta['requirements'][kind]:
                        if _have_recipe(dep):
                            _copy_recipe(dep)

            # add to list of products, and decide if we need to rebuild it
            assert name not in self.products

            # Load name+version from meta.yaml
            import yaml
            with open(os.path.join(dest, 'meta.yaml')) as fp:       # FIXME: meta.yaml configs are not true .yaml files; this may fail in the future
                meta = yaml.load(fp)
            assert meta['package']['name'] == name, "meta['package']['name'] != name :::: (%s, %s)" % (meta['package']['name'], name)

            #
            # Check if this package has already been built, by looking for a built
            # package with the same name, version and build number
            #
            version = meta['package']['version']
            buildnum = 0
            build_string = "py27_0"
            if 'build' in meta:
                buildnum     = meta['build'].get('number', buildnum)
                build_string = meta['build'].get('number', build_string)
            try:
                ret = subprocess.check_output('conda search --use-local --spec --json %s=%s' % (name, version), shell=True).strip()
                j = json.loads(ret)
                for pkginfo in j.get(str(name), []):
                    if pkginfo[u'build_number'] == buildnum:
                        is_built = True
                        break
                else:
                    is_built = False
            except subprocess.CalledProcessError as e:
                # it's OK to fail on an uninitialized conda-bld/<platform> directory.
                # TODO: the way we test for this is pretty ugly, but I can't think of a better way yet
                j = json.loads(e.output)
                if (j[u'error_type'] == 'NoPackagesFound') or (j[u'error_type'] == "RuntimeError" and j[u'error'].startswith("Could not find URL: file:///")):
                    is_built = False
                else:
                    raise

            self.products[name] = ProductInfo(name, version, build_string, buildnum, None, None, is_built, False)

            self.report_progress(name, self.products[name].version)

        recipe = _have_recipe(name)
        if recipe is None:
            raise Exception("A package depends on '%s', but there's no recipe to build it in '%s'" % (name, additional_recipes_dir))

        _copy_recipe(name)

    def add_missing_deps(self, conda_name):
        # inject missing dependencies, creating new conda packages if needed
        # returns Conda package names

        deps_ = { 'build': [], 'run': [] }
        for typ, deps in list(deps_.items()):
            for (kind, dep, verSpec, selector, pkgSpec) in self.config.get_missing_deps(conda_name, typ):
                # print '----', conda_name, ':', typ, kind, dep, verSpec, selector, pkgSpec
                {
                        'recipe': self.copy_additional_recipe,
                }.get(kind, lambda dep: None)(dep)
                deps.append(pkgSpec)

        return deps_['build'], deps_['run']

    def generate(self, manifest):
        # Generate conda package files and build driver script
        shutil.rmtree(self.config.output_dir, ignore_errors=True)
        os.makedirs(self.config.output_dir)
        print("generating recipes: ")
        for (product, sha, version, deps) in manifest.values():
            if product in self.config.skip_products: continue

            # override gitrevs (these are temporary hacks/fixes; they should go away when those branches are merged)
            sha = self.config.override_gitrev.get(product, sha)

            # Where is the source?
            giturl = self.config.get_giturl(product)
            self.gen_conda_package(product, sha, version, giturl, deps)
        print("done.")

        #
        # write out the rebuild script for packages that need rebuilding
        #
        rebuilds = []
        print("generating rebuild script:")
        for pi in self.products.values():
            conda_version = "%s-%s" % (pi.version, pi.build_string)

            rebuilds.append("rebuild %s %s %s %s" % (pi.conda_name, conda_version, pi.product, pi.eups_version))
            if not pi.is_built:
                print("  will build:    %s-%s" % (pi.conda_name, conda_version))
            else:
                with open(os.path.join(self.config.output_dir, pi.conda_name, '.done'), 'w'):   # create the .done marker file
                    pass
                print("  already built: %s-%s" % (pi.conda_name, conda_version))

            if pi.conda_name in self.config.skip_build:
                # create the .skip.$PLATFORM marker files
                for platform in self.config.skip_build[pi.conda_name]:
                    with open(os.path.join(self.config.output_dir, pi.conda_name, '.skip.'+platform), 'w'):
                        pass
                print("    (builds will always be skipped on %s)" % ', '.join(self.config.skip_build[pi.conda_name]))

        print("done.")

        fill_out_template(os.path.join(self.config.output_dir, 'rebuild.sh'), os.path.join(self.config.template_dir, 'rebuild.sh.template'),
                output_dir = self.config.output_dir,
                rebuilds = '\n'.join(rebuilds)
                )
