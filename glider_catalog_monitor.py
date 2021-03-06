#!/usr/bin/env python
import os
import time
import json
import argparse
import logging
from watchdog.events import FileSystemEventHandler, DirCreatedEvent, FileModifiedEvent, DirModifiedEvent
from watchdog.observers import Observer
from lxml import etree

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s | %(levelname)s]  %(message)s')
logger = logging.getLogger(__name__)

RSYNC_TO_PATH = os.environ.get("RSYNC_TO_PATH")
DEV_CATALOG_ROOT = os.environ.get("DEV_CATALOG_ROOT")

class HandleMission(FileSystemEventHandler):
    def __init__(self, base, catalog):
        self.base     = base
        self.catalog  = catalog

    def on_created(self, event):

        rel_path = os.path.relpath(event.src_path, self.base)
        path_parts = rel_path.split(os.sep)

        if isinstance(event, DirCreatedEvent):
            # expecting a user/mission
            if len(path_parts) != 2:
                return
            logger.info("New mission directory: %s", rel_path)
            logger.info("Creating catalog and NcML Aggregations")
            self._create_ncml(user=path_parts[0], mission=path_parts[1])
            self._create_catalog(user=path_parts[0], mission=path_parts[1])
        else: # FileCreated
            # expecting a user/mission/file
            if len(path_parts) != 3:
                return
            if path_parts[-1] == "mission.json":
                logger.info("Creating Catalog and NcML Aggregations with new Mission metadata")
                self._create_ncml(user=path_parts[0], mission=path_parts[1])
                self._create_catalog(user=path_parts[0], mission=path_parts[1])
            pass

    def on_modified(self, event):

        rel_path = os.path.relpath(event.src_path, self.base)
        path_parts = rel_path.split(os.sep)

        if isinstance(event, DirModifiedEvent):
            # expecting a user/mission
            if len(path_parts) != 2:
                return
            logger.info("Directory modified: %s", rel_path)
            logger.info("Recreating catalog and NcML Aggregations")
            self._create_ncml(user=path_parts[0], mission=path_parts[1])
            self._create_catalog(user=path_parts[0], mission=path_parts[1])
        elif isinstance(event, FileModifiedEvent):
            # expecting a user/mission/file
            if len(path_parts) != 3:
                return
            if path_parts[-1] == "mission.json":
                logger.info("Recreating Catalog and NcML Aggregations with modified Mission metadata")
                self._create_ncml(user=path_parts[0], mission=path_parts[1])
                self._create_catalog(user=path_parts[0], mission=path_parts[1])

    def _create_catalog(self, user, mission):

        dir_path    = os.path.join(self.base, user, mission)
        cat_path    = os.path.join(self.catalog, user, mission)

        time_path   =  os.path.join(cat_path, "timeagg.ncml")
        timeuv_path =  os.path.join(cat_path, "timeuvagg.ncml")

        # Load Misson JSON if is exists.  We want to pull information from this JSON
        # and not rely on the directory structure if possible.
        title        = user
        mission_name = mission
        wmo_id       = "NotAssigned"
        try:
          with open(os.path.join(dir_path, "mission.json")) as f:
            js           = json.load(f)
            title        = js['operator']
            if title is None or title == "":
              title = js['username']
            mission_name = js['name']
            wmo_id       = js['wmo_id'].strip()
        except (OSError, IOError, AssertionError, AttributeError):
          pass
        finally:
          title        = slugify(title)
          mission_name = slugify(mission_name)

        try:
            os.makedirs(cat_path)
        except OSError:
            # Dir Already exists
            pass

        cat_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <catalog name="IOOS Glider DAC - %(title)s - %(mission)s Catalog"
         xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink">

          <service name="agg" base="" serviceType="compound">
            <service name="odap" serviceType="OpenDAP" base="/thredds/dodsC/" />
            <service name="ncml" serviceType="NCML" base="/thredds/ncml/" />
            <service name="uddc" serviceType="UDDC" base="/thredds/uddc/" />
            <service name="iso" serviceType="ISO" base="/thredds/iso/"/>
            <service name="sos" serviceType="SOS" base="/thredds/sos/" />
          </service>

          <dataset name="%(title)s - %(mission_name)s - Time Aggregation" ID="%(title)s_%(mission_name)s_Time" urlPath="%(title)s_%(mission_name)s_Time.ncml">
            <serviceName>agg</serviceName>
            <netcdf xmlns="http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2" location="%(time_path)s" />
          </dataset>

          <dataset name="%(title)s - %(mission_name)s - Depth Averaged Aggregation" ID="%(title)s_%(mission_name)s_TimeUV" urlPath="%(title)s_%(mission_name)s_TimeUV.ncml">
            <serviceName>agg</serviceName>
            <netcdf xmlns="http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2" location="%(timeuv_path)s" />
          </dataset>
        </catalog>
        """ % locals()

        with open(os.path.join(cat_path, "catalog.xml"), 'w') as f:
            f.write(cat_xml)

        # create individual files catalog
        cat_indv_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <catalog name="IOOS Glider DAC - %(title)s - %(mission)s Catalog (Individual Files)"
         xmlns="http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
         xmlns:xlink="http://www.w3.org/1999/xlink">

          <service name="all" base="" serviceType="compound">
            <service name="odap" serviceType="OpenDAP" base="/thredds/dodsC/" />
            <service name="http" serviceType="HTTPServer" base="/thredds/fileServer/" />
            <service name="ncml" serviceType="NCML" base="/thredds/ncml/" />
            <service name="uddc" serviceType="UDDC" base="/thredds/uddc/" />
            <service name="iso" serviceType="ISO" base="/thredds/iso/"/>
            <service name="sos" serviceType="SOS" base="/thredds/sos/" />
          </service>

          <datasetScan name="%(title)s - %(mission_name)s - Individual Files" ID="%(title)s_%(mission_name)s_Files" path="%(title)s_%(mission_name)s_Files" location="%(dir_path)s">
            <metadata inherited="true">
              <serviceName>all</serviceName>
            </metadata>
            <filter>
              <include wildcard="*.nc"/>
            </filter>
            <netcdf xmlns="http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2">
              <variable name="platform">
                <attribute name="wmo_id" value="%(wmo_id)s" />
              </variable>
            </netcdf>
          </datasetScan>
        </catalog>
        """ % locals()

        with open(os.path.join(cat_path, "catalog-individual.xml"), 'w') as f:
            f.write(cat_indv_xml)

    def _create_ncml(self, user, mission):

        dir_path = os.path.join(self.base, user, mission)
        cat_path = os.path.join(self.catalog, user, mission)

        try:
            os.makedirs(cat_path)
        except OSError:
            # Dir Already exists
            pass

        # Add WMO ID if it exists
        try:
          with open(os.path.join(dir_path, "mission.json")) as f:
            js     = json.load(f)
            wmo_id = js['wmo_id'].strip()
            assert len(wmo_id) > 0
        except (IOError, AssertionError, AttributeError):
          # No wmoid.txt file
          wmo_id = "NotAssigned"

        time_agg = """<?xml version="1.0" encoding="UTF-8"?>
            <netcdf xmlns="http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2">
              <remove type="variable" name="time_uv"/>
              <remove type="variable" name="lat_uv"/>
              <remove type="variable" name="lon_uv"/>
              <remove type="variable" name="u"/>
              <remove type="variable" name="u_qc"/>
              <remove type="variable" name="v_qc"/>

              <variable name="platform">
                <attribute name="wmo_id" value="%(wmo_id)s" />
              </variable>

              <aggregation dimName="time" type="joinExisting" recheckEvery="5 min">
                <scan location="%(dir_path)s" suffix=".nc" subdirs="false" />
              </aggregation>
            </netcdf>
            """ % locals()

        with open(os.path.join(cat_path, "timeagg.ncml"), 'w') as f:
            f.write(time_agg)


        time_uv_agg = """<?xml version="1.0" encoding="UTF-8"?>
            <netcdf xmlns="http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2">
              <remove type="variable" name="time"/>
              <remove type="variable" name="time_qc"/>
              <remove type="variable" name="segment_id"/>
              <remove type="variable" name="profile_id"/>
              <remove type="variable" name="depth"/>
              <remove type="variable" name="depth_qc"/>
              <remove type="variable" name="lat"/>
              <remove type="variable" name="lat_qc"/>
              <remove type="variable" name="lon"/>
              <remove type="variable" name="lon_qc"/>
              <remove type="variable" name="pressure"/>
              <remove type="variable" name="pressure_qc"/>
              <remove type="variable" name="conductivity"/>
              <remove type="variable" name="conductivity_qc"/>
              <remove type="variable" name="density"/>
              <remove type="variable" name="density_qc"/>
              <remove type="variable" name="salinity"/>
              <remove type="variable" name="salinity_qc"/>
              <remove type="variable" name="temperature"/>
              <remove type="variable" name="temperature_qc"/>

              <variable name="platform">
                <attribute name="wmo_id" value="%(wmo_id)s" />
              </variable>

              <aggregation dimName="time_uv" type="joinExisting" recheckEvery="5 min">
                <scan location="%(dir_path)s" suffix=".nc" subdirs="false" />
              </aggregation>
            </netcdf>
            """ % locals()

        with open(os.path.join(cat_path, "timeuvagg.ncml"), 'w') as f:
            f.write(time_uv_agg)

def slugify(value):
    """
    Normalizes string, removes non-alpha characters, and converts spaces to hyphens.
    Pulled from Django
    """
    import unicodedata
    import re
    value = unicode(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
    value = unicode(re.sub('[^\w\s-]', '', value).strip())
    return unicode(re.sub('[-\s]+', '-', value))

def main(handler):
    observer = Observer()
    observer.schedule(handler, path=handler.base, recursive=True)
    observer.start()
    logger.info("Watching user directories in %s", handler.base)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('basedir',
                        default=RSYNC_TO_PATH,
                        nargs='?')
    parser.add_argument('catalogdir',
                        default=DEV_CATALOG_ROOT,
                        nargs='?')
    args = parser.parse_args()
    base = os.path.realpath(args.basedir)
    catalog = os.path.realpath(args.catalogdir)
    main(HandleMission(base, catalog))
