import luigi
import json
import time
import re
import datetime
import subprocess
import base64
from urllib import urlopen
from uuid import uuid4
from elasticsearch import Elasticsearch

# TODO
# * I think we want to use S3 for our touch files (aka lock files) since that will be better than local files that could be lost/deleted

class ConsonanceTask(luigi.Task):
    redwood_host = luigi.Parameter("storage2.ucsc-cgl.org")
    redwood_token = luigi.Parameter("must_be_defined")
    dockstore_tool_running_dockstore_tool = luigi.Parameter(default="quay.io/briandoconnor/dockstore-tool-running-dockstore-tool:1.0.0")
    target_tool = luigi.Parameter(default="quay.io/wshands/fastqc")
    filenames = luigi.ListParameter(default=["filename"])
    file_uuids = luigi.ListParameter(default=["uuid"])
    bundle_uuids = luigi.ListParameter(default=["bundle_uuid"])
    # TODO: just modeling this as a string comma sep, need to actually ensure this is a JSON array
    parent_uuids = luigi.ListParameter(default=["parent_uuid1"])
    tmp_dir = luigi.Parameter(default='/tmp')
    new_uuid = str(uuid4())

    def run(self):
        print "** EXECUTING IN CONSONANCE **"
        print "** MAKE TEMP DIR **"
        # create a unique temp dir
        cmd = '''mkdir -p %s/consonance-jobs/%s/''' % (self.tmp_dir, self.new_uuid)
        print cmd
        print "** MAKE JSON FOR WORKER **"
        # create a json for FastQC which will be executed by the dockstore-tool-running-dockstore-tool and passed as base64encoded
        # will need to encode the JSON above in this: https://docs.python.org/2/library/base64.html
        # see http://luigi.readthedocs.io/en/stable/api/luigi.parameter.html?highlight=luigi.parameter
        # TODO: this is tied to the requirements of the tool being targeted
        json_str = '''{
"fastq_file": [
        '''
        i = 0
        while i<len(self.filenames):
            # append file information
            json_str += '''
{
    "class": "File",
    "path": "redwood://%s/%s/%s/%s"
}
            ''' % (self.redwood_host, self.bundle_uuids[i], self.file_uuids[i], self.filenames[i])
            if i < len(self.filenames) - 1:
                json_str += ","
            i += 1
        json_str += ''']
}
        '''
        # now make base64 encoded version
        base64_json_str = base64.urlsafe_b64encode(json_str)
        print "** MAKE JSON FOR DOCKSTORE TOOL WRAPPER **"
        # create a json for dockstoreRunningDockstoreTool, embed the FastQC JSON as a param
        p = self.output()[0].open('w')
        print >>p, '''{
            "json_encoded": "%s",
            "dockstore_uri": "%s",
            "redwood_token": "%s",
            "redwood_host": "%s",
            "parent_uuids": "[%s]"
        }''' % (base64_json_str, self.target_tool, self.self.redwood_token, self.self.redwood_host, ','.join(map("'{0}'".format, self.parent_uuids)))
        p.close()
        # execute consonance run, parse the job UUID
        print "** SUBMITTING TO CONSONANCE **"
        print "consonance run  --flavour m1.xlarge --image-descriptor Dockstore.cwl --run-descriptor sample_configs.json"
        # loop to check the consonance status until finished or failed
        print "** WAITING FOR CONSONANCE **"
        print "consonance status --job_uuid e2ad3160-74e2-4b04-984f-90aaac010db6"
#        result = subprocess.call(cmd, shell=True)
#        if result == 0:
#            cmd = "rm -rf "+self.data_dir+"/"+self.bundle_uuid+"/bamstats_report.zip "+self.data_dir+"/"+self.bundle_uuid+"/datastore/"
#            print "CLEANUP CMD: "+cmd
#            result = subprocess.call(cmd, shell=True)
#            if result == 0:
#                print "CLEANUP SUCCESSFUL"
#            f = self.output().open('w')
#            print >>f, "uploaded"
#            f.close()

    def output(self):
        return luigi.LocalTarget('%s/consonance-jobs/%s/finished' % (self.tmp_dir, self.new_uuid))

class SequenceQCCoordinator(luigi.Task):

    es_index_host = luigi.Parameter(default='localhost')
    es_index_port = luigi.Parameter(default='9200')
    redwood_token = luigi.Parameter("must_be_defined")
    redwood_storage_client_path = luigi.Parameter(default='../ucsc-storage-client')
    redwood_host = luigi.Parameter(default='storage2.ucsc-cgl.org')
    dockstore_tool_running_dockstore_tool = luigi.Parameter(default="quay.io/briandoconnor/dockstore-tool-running-dockstore-tool:1.0.0")
    tmp_dir = luigi.Parameter(default='/tmp')
    data_dir = luigi.Parameter(default='/tmp/data_dir')
    max_jobs = luigi.Parameter(default='1')
    bundle_uuid_filename_to_file_uuid = {}

    def requires(self):
        print "** COORDINATOR **"
        # now query the metadata service so I have the mapping of bundle_uuid & file names -> file_uuid
        json_str = urlopen(str("https://"+self.redwood_host+":8444/entities?page=0")).read()
        metadata_struct = json.loads(json_str)
        print "** METADATA TOTAL PAGES: "+str(metadata_struct["totalPages"])
        for i in range(0, metadata_struct["totalPages"]):
            print "** CURRENT METADATA TOTAL PAGES: "+str(i)
            json_str = urlopen(str("https://"+self.redwood_host+":8444/entities?page="+str(i))).read()
            metadata_struct = json.loads(json_str)
            for file_hash in metadata_struct["content"]:
                self.bundle_uuid_filename_to_file_uuid[file_hash["gnosId"]+"_"+file_hash["fileName"]] = file_hash["id"]

        # now query elasticsearch
        es = Elasticsearch([{'host': self.es_index_host, 'port': self.es_index_port}])
        # see jqueryflag_alignment_qc
        # curl -XPOST http://localhost:9200/analysis_index/_search?pretty -d @jqueryflag_alignment_qc
        #res = es.search(index="analysis_index", body={"query":{"filtered":{"filter":{"bool":{"must":{"or":[{"terms":{"flags.normal_sequence_qc_report":["false"]}},{"terms":{"flags.tumor_sequence_qc_report":["false"]}}]}}},"query":{"match_all":{}}}}}, size=5000)
        res = es.search(index="analysis_index", body={"query" : {"bool" : {"should" : [{"term" : { "flags.normal_sequence_qc_report" : "false"}},{"term" : {"flags.tumor_sequence_qc_report" : "false" }}],"minimum_should_match" : 1 }}}, size=5000)

        listOfJobs = []

        print("Got %d Hits:" % res['hits']['total'])
        for hit in res['hits']['hits']:
            print("%(donor_uuid)s %(center_name)s %(project)s" % hit["_source"])
            for specimen in hit["_source"]["specimen"]:
                for sample in specimen["samples"]:
                    for analysis in sample["analysis"]:
                        #print "MAYBE HIT??? "+analysis["analysis_type"]+" "+str(hit["_source"]["flags"]["normal_sequence_qc_report"])+" "+specimen["submitter_specimen_type"]
                        if analysis["analysis_type"] == "sequence_upload" and ((hit["_source"]["flags"]["normal_sequence_qc_report"] == False and re.match("^Normal - ", specimen["submitter_specimen_type"])) or (hit["_source"]["flags"]["tumor_sequence_qc_report"] == False and re.match("^Primary tumour - |^Recurrent tumour - |^Metastatic tumour -", specimen["submitter_specimen_type"]))):
                            #print analysis
                            print "HIT!!!! "+analysis["analysis_type"]+" "+str(hit["_source"]["flags"]["normal_sequence_qc_report"])+" "+specimen["submitter_specimen_type"]
                            files = []
                            file_uuids = []
                            bundle_uuids = []
                            parent_uuids = []
                            for file in analysis["workflow_outputs"]:
                                if (file["file_type"] == "fastq"):
                                    # this will need to be an array
                                    files.append(file["file_path"])
                                    file_uuids.append(self.fileToUUID(file["file_path"], analysis["bundle_uuid"]))
                                    bundle_uuids.append(analysis["bundle_uuid"])
                                    parent_uuids.append(sample["sample_uuid"])
                            print "  + will run report for %s" % files
                            if len(listOfJobs) < int(self.max_jobs):
                                listOfJobs.append(ConsonanceTask(redwood_host=self.redwood_host, redwood_token=self.redwood_token, dockstore_tool_running_dockstore_tool=self.dockstore_tool_running_dockstore_tool, filenames=files, file_uuids = file_uuids, bundle_uuids = bundle_uuids, parent_uuids = parent_uuids, tmp_dir=self.tmp_dir))
                                # target_tool= # TODO: fill in params filenames=['']
                                #redwood_storage_client_path=self.redwood_storage_client_path, redwood_host=self.redwood_host, filename=bamFile, uuid=self.fileToUUID(bamFile, analysis["bundle_uuid"]), bundle_uuid=analysis["bundle_uuid"], parent_uuid=sample["sample_uuid"], tmp_dir=self.tmp_dir, data_dir=self.data_dir))

        # these jobs are yielded to
        return listOfJobs

    def run(self):
        # now make a final report
        f = self.output().open('w')
        # TODO: could print report on what was successful and what failed?  Also, provide enough details like donor ID etc
        print >>f, "batch is complete"
        f.close()

    def output(self):
        # the final report
        ts = time.time()
        ts_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H:%M:%S')
        return luigi.LocalTarget('%s/consonance-jobs/SequenceQCTask-%s.txt' % (self.tmp_dir, ts_str))

    def fileToUUID(self, input, bundle_uuid):
        return self.bundle_uuid_filename_to_file_uuid[bundle_uuid+"_"+input]
        #"afb54dff-41ad-50e5-9c66-8671c53a278b"

if __name__ == '__main__':
    luigi.run()
