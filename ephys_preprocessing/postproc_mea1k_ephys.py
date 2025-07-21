import os
import time
import json

import numpy as np
import pandas as pd

import h5py

from CustomLogger import CustomLogger as Logger
import analytics_processing.sessions_from_nas_parsing as sp
import analytics_processing.modality_loading as ml
from analytics_processing.analytics_constants import device_paths
from sklearn.linear_model import LinearRegression

from scipy.signal import butter
from scipy.signal import filtfilt

# slow imports requing C compilation
from sklearn.decomposition import FastICA
from sklearn.model_selection import GridSearchCV
from sklearn.svm import SVC
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, balanced_accuracy_score


from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from scipy.linalg import subspace_angles

from scipy.stats import pearsonr
import matplotlib.pyplot as plt

from dashsrc.plot_components.plot_utils import make_discr_cluster_id_cmap

# from ../../ephysVR.git
from mea1k_modules.mea1k_raw_preproc import mea1k_raw2decompressed_dat_file

def postprocess_ephys(**kwargs):
    L = Logger()
    exclude_shanks = kwargs.pop("exclude_shanks")
    mode = kwargs.pop("mode")
    
    sessionlist_fullfnames, ids = sp.sessionlist_fullfnames_from_args(**kwargs)

    for i, (session_fullfname, identif) in enumerate(zip(sessionlist_fullfnames, ids)):
        L.logger.info(f"Processing {identif} ({i+1}/{len(ids)}) "
                      f"{os.path.basename(session_fullfname)}"
                       f"\n{os.path.dirname(session_fullfname)}")
        
        # create the dat file 
        session_name = os.path.basename(session_fullfname).replace(".hdf5", "")
        session_dir = os.path.dirname(session_fullfname)
        animal_name = session_name.split("_")[2]
        
        # check if a dat file already exists
        dat_fnames = [f for f in os.listdir(session_dir) if f.endswith("ephys_traces.dat")]
        dat_sizes = np.array([os.path.getsize(os.path.join(session_dir, f)) for f in dat_fnames])

        if any(dat_sizes>0):
            L.logger.debug(f"De-compressed ephys files found: {dat_fnames}")
            if mode != "recompute":
                L.logger.debug(f"Skipping...")
                continue
            else:
                L.logger.debug(f"Recomputing...")
            
        if os.path.exists(os.path.join(session_dir, "ephys_output.raw.h5")):
            fname = 'ephys_output.raw.h5'
        elif os.path.exists(os.path.join(session_dir, f"{session_name}_ephys_logger.raw.h5")):
            fname = f"{session_name}_ephys_logger.raw.h5"
        else:
            L.logger.warning(f"No raw ephys recordings found for {session_name}")
            continue

        # decompress the raw output of mea1k and convert to uV int16 .dat file
        # also, save a mapping csv file for identifying the rows in the dat file
        mea1k_raw2decompressed_dat_file(session_dir, 
                                        fname=fname, 
                                        session_name=session_name,
                                        animal_name=animal_name,
                                        convert2uV=True,
                                        subtract_dc_offset=True,
                                        write_neuroscope_xml=True,
                                        write_probe_file=True,
                                        replace_with_curated_xml=False,
                                        exclude_shanks=exclude_shanks)
        
        
        
        
        
        
        
        
        
        
def extract_jrc_spikes(session_fullfname): #, get_spikes=False, 
                                           #    get_cluster_metadata=False, get_spikes_cluster_subset=None):
    L = Logger()
    
    def ssbatch_cluster_metadata(ss_res_fullfname):
        # open jrc output to read cluster /specifc unit metadata, excluding single spikes
        with h5py.File(ss_res_fullfname, 'r') as f:
            cluster_notes_data = []
            # unpack jrc's messy notes
            for note_raw in [f[obj_ref][()] for obj_ref in f['clusterNotes'][0]]:
                cluster_notes_data.append("".join([chr(c.item()) for c in note_raw]))
            cluster_notes_data = [n if n != '\x00\x00' else '' for n in cluster_notes_data]
            clust_id = np.sort(np.unique(f['spikeClusters'][0]))
            clust_id = clust_id[~np.isin(clust_id, (-1, 0))].astype(int)
            cluster_table = pd.DataFrame({
                "cluster_id": clust_id +(10_000*ss_i), # make ids unique
                "cluster_type": cluster_notes_data,
                "unit_count": f['unitCount'][0],
                "cluster_channel": f['clusterSites'][:, 0]-1, # matlab 1-based index
                "cluster_id_ssbatch": clust_id,
                "unit_snr": f['unitSNR'][0],
                "unit_Vpp": f['unitVpp'][0] /6.3, # error in JRC settings, reset here, TODO rm later
                "unit_isi_ratio": f['unitISIRatio'][:,0],
                "unit_iso_dist": f['unitIsoDist'][:,0],
                "unit_L_ratio": f['unitLRatio'][:,0],
            })
        cluster_table['session_nsamples'] = traces.shape[1]
        cluster_table['ss_batch_name'] = ss_dirname
        cluster_table['ss_batch_id'] = ss_i

        # merge in useful metadata from ephys mapping.csv
        mapping_cols = ['amplifier_id', 'mea1k_el', 'pad_id', 'metal', 'shank_name', 
                        'el_pair', 'mea1k_connectivity', 'connectivity_order',
                        'shank_side', 'curated_trace', 'depth', 'shank_id', 
                        'gross_brain_area', 'fine_brain_area']
        cluster_metad = mapping.loc[cluster_table.cluster_channel, mapping_cols].drop_duplicates()
        cluster_metad = cluster_metad.reset_index().rename({'index': 'cluster_channel',
                                                            'el_pair': 'fiber_id'}, axis=1)
        cluster_table = pd.merge(cluster_table, cluster_metad, on='cluster_channel')
        cluster_table = cluster_table[~np.isin(cluster_table.cluster_type, ('to_delete', ""))]
        L.logger.debug(f"Spike cluster table:\n{cluster_table}")
        return cluster_table

    def aggr_spike_cluster_metadata(cluster_aggr_over_ss_batches):
        # first process the spike metadata, merge them and create unique cluster ids, crucial
        # TODO add in session_wise spike count from spikes below? add average waveforms?
        # TODO add brain region to schema
        sp_clust_metadata = pd.concat(cluster_aggr_over_ss_batches, axis=0)
        
        unique_ids = sp_clust_metadata.cluster_id.unique() # unique because of + 10_000*ss_i
        # new ids start at 1 and go go up to the number of unique ids
        renamer = {old_id: new_id+1 for new_id, old_id in enumerate(unique_ids)}
        sp_clust_metadata['cluster_id'] = sp_clust_metadata['cluster_id'].replace(renamer)
        
        # assign colors per cluster    
        map_colors = np.vectorize(make_discr_cluster_id_cmap(sp_clust_metadata['cluster_id']).get)
        sp_clust_metadata['cluster_color'] = map_colors(sp_clust_metadata['cluster_id'])
        sp_clust_metadata['cluster_id_str'] = [f"Unit{c_id:04d}" for c_id in sp_clust_metadata['cluster_id']]
        return sp_clust_metadata

    def ssbatch_process_spikes(ss_res_fullfname, session_from_smple, session_to_smple):
        # open jrc output to read single spikes in a the interval matching the session
        with h5py.File(ss_res_fullfname, 'r') as f:
            ss_spike_times = f['spikeTimes'][0]
            ss_from_spike_i = np.where((session_from_smple < ss_spike_times))[0][0]
            ss_to_spike_i = np.where((session_to_smple < ss_spike_times))[0]
            if len(ss_to_spike_i) != 0:
                ss_to_spike_i = ss_to_spike_i[0]
            else:
                # last spike before end of session
                ss_to_spike_i = len(ss_spike_times)-1
            L.logger.debug(f"Session samples within concatenated data conext go"
                        f" from {session_from_smple:,} to {session_to_smple:,}." 
                        f"All spike ({len(ss_spike_times):,}) go from sample {ss_spike_times[0]:,} to {ss_spike_times[-1]:,}."
                        f" This session's spikes are at: [{ss_spike_times[ss_from_spike_i]:,} ... {ss_spike_times[ss_to_spike_i]:,}]")
            
            spike_times = ss_spike_times[ss_from_spike_i:ss_to_spike_i]
            spike_clusters = f['spikeClusters'][0, ss_from_spike_i:ss_to_spike_i]
            spike_amps = f['spikeAmps'][0, ss_from_spike_i:ss_to_spike_i]
            spike_positions = f['spikePositions'][0, ss_from_spike_i:ss_to_spike_i]
            spike_sites = f['spikeSites'][0, ss_from_spike_i:ss_to_spike_i]
            spike_sites_2nd = f['spikeSites2'][0, ss_from_spike_i:ss_to_spike_i]
            if f['spikeSites3'].shape == (2,): # JRC output might not have 3rd site
                spike_sites_3rd = np.array([np.nan]*len(spike_sites_2nd))
                nsites = 2
            else: 
                spike_sites_3rd = f['spikeSites3'][0, ss_from_spike_i:ss_to_spike_i]
                nsites = 3
        
        spike_table = pd.DataFrame({
            "sample_id": spike_times-session_from_smple,
            "ephys_timestamp": (spike_times-session_from_smple).astype(np.uint64)*50,
            "cluster_id_ssbatch": spike_clusters.astype(int),
            "channel": spike_sites-1, # matlab 1-based index
            "amplitude_uV": spike_amps /6.3, # error in JRC settings, reset here, TODO rm later
            "ss_batch_id": ss_i,
            # "channel_hpf_wf": pd.NA,
            # "channel_2nd_hpf_wf": pd.NA,
            # "channel_3rd_hpf_wf": pd.NA,
            "channel_2nd": spike_sites_2nd-1, # matlab 1-based index
            "channel_3rd": spike_sites_3rd-1, # matlab 1-based index
            "shank": np.round(spike_positions)//1000, # convert back from original shank * 1000
        })
        
        # remove hard deleted clusters, using backspace in JRC (-1)
        spike_table = spike_table.loc[spike_table.cluster_id_ssbatch!=-1].reset_index(drop=True)

        # # TODO this was neccessary before
        # print(spike_table)
        # if get_spikes_cluster_subset is not None:
        #     print(get_spikes_cluster_subset)
        #     incl_clust = get_spikes_cluster_subset[get_spikes_cluster_subset.ss_batch_id == ss_i].cluster_id_ssbatch
        #     spike_table = spike_table[spike_table.cluster_id_ssbatch.isin(incl_clust)]
        # print(spike_table)
        # exit()
        
        # drop ISI violations, targeting case: same cluster, different site, ISI < 1ms
        def drop_isi_viol(cluster_spikes):
            isi = np.diff(cluster_spikes.ephys_timestamp.values)
            return cluster_spikes.iloc[np.where(isi > 1_000)[0]+1]
        prv_nspikes = spike_table.shape[0]
        spike_table = spike_table.groupby('cluster_id_ssbatch').apply(drop_isi_viol)
        
        # add depth
        spike_table['depth'] = mapping.depth.values[spike_table.channel]
        spike_table = spike_table.sort_values(by=['sample_id']).reset_index(drop=True)
        L.logger.debug(f"Extracted spikes from {spike_table.cluster_id_ssbatch.nunique():,} "
                       f" unique clusters, dropped {prv_nspikes - spike_table.shape[0]:,} "
                       f" spikes for ISI violations.\n{spike_table}")
        return spike_table, nsites
        
    def aggr_spikes(spike_aggr_over_ss_batches, sp_clust_metadata):    
        # after metadata is processed, we can process the single spikes
        spikes = pd.concat(spike_aggr_over_ss_batches, axis=0)

        spikes.sort_values(by='sample_id', inplace=True) # to be sure

        # use processed sp_clust_metadata to assign unique cluster ids to spikes
        # create a mapping between non_unique cluster ids from seperate spike sorting 
        # batches to unique ids in metadata
        unq_id_renamer = (sp_clust_metadata.loc[:, ['cluster_id_ssbatch', 'ss_batch_id']].values).tolist()
        unq_id_renamer = {str(k): c_id for k, c_id in zip(unq_id_renamer, sp_clust_metadata.cluster_id)}

        # use the mapping to assign unique cluster ids to single spikes
        keys = [str(k) for k in spikes.loc[: , ['cluster_id_ssbatch', 'ss_batch_id']].values.tolist()]
        spikes['cluster_id'] = [unq_id_renamer.get(k, 0) for k in keys]
        spikes['cluster_id_str'] = spikes['cluster_id'].apply(lambda x: f"Unit{x:04d}")

        # add cluster color for each spike
        cols = sp_clust_metadata.set_index('cluster_id').reindex(spikes['cluster_id']).cluster_color
        spikes['cluster_color'] = cols.fillna('#888888').values # needed bc of cl_id == 0 or not in metadata yet (sorted)
        
        # add brain region
        spikes = pd.merge(spikes, sp_clust_metadata[['cluster_id', 'gross_brain_area', 'fine_brain_area']],
                          on='cluster_id', how='left')
        spikes = spikes[np.isin(spikes.cluster_id, sp_clust_metadata.cluster_id)]
        return spikes.reset_index(drop=True)
    
    def extract_waveforms(spike_table, nsites):
        def process_spike_chunk(spike_table_chunk, sos_filter):
            # create the time window around the spike chunk
            from_smple, to_smple = spike_table_chunk.iloc[[0,-1]].sample_id.values
            from_smple = max(from_smple - filt_window//2, 0)
            to_smple = min(to_smple + filt_window//2, traces.shape[1])
            # realign spike sample_ids to the chunk, starting from 0
            spike_table_chunk.loc[:, 'sample_id'] -= from_smple
            # read raw data to memory
            traces_chunk = np.array(traces[:, from_smple:to_smple], dtype=np.int16)
            
            # create the channel index, one flat list is the final output
            rows_2d = spike_table_chunk.loc[:, chnls_str].values
            rows_flat = np.repeat(rows_2d.flatten(), filt_window)
            
            # create the tinewindows, repeat index for filtwindow & site to make flat
            t = np.repeat(spike_table_chunk.sample_id.values, nsites) # peaks, nsites
            cols_2d = np.row_stack([np.arange(-filt_window//2, filt_window//2)]*len(t)) +t[:, None] # expand over window
            cols_2d = np.clip(cols_2d, 0, traces_chunk.shape[1]-1) # ensure within sample bounds
            cols_flat = cols_2d.flatten()
            
            waveforms = traces_chunk[rows_flat, cols_flat].reshape(nsites, spike_table_chunk.shape[0], filt_window)
            t2 = time.time()

            # iterate over the sites and filter the waveforms
            all_filt_wfs = [[] for _ in range(nsites)]
            for sp_i in range(waveforms.shape[1]):
                for site_k in range(nsites):
                    filt_wf = np.round(filtfilt(*sos_filter, waveforms[site_k, sp_i, :])).astype(np.int16)
                    all_filt_wfs[site_k].append(filt_wf[filt_window//2 -10:-filt_window//2 +25])
            # print(f"Filtered waveforms took {time.time()-t2:.3f} s")
            
            # instert spike waveform into spike_table
            all_filt_wfs_aggr = []
            for site_k, col_name in enumerate(chnls_str):
                all_filt_wfs_aggr.append(pd.Series(all_filt_wfs[site_k], 
                                                    name=col_name+'_hpf_wf',))
            return pd.concat(all_filt_wfs_aggr, axis=1)
        
        # # skip this if don't want to wait 20 minutes per sessions
        # TODO parallelize this once server reads are concurrent
        L.logger.debug(f"Extracting wavefroms & filtering...")
        nspikes_per_read = 10
        filt_window = 512
        chnls_str = ['channel', 'channel_2nd', 'channel_3rd'] if nsites == 3 else ['channel', 'channel_2nd']
        
        sos_filter = butter(4, [300, 5000], btype='band', fs=20_000)
        start_t = time.time()
        # for chunk_i in range(spike_table.shape[0] //nspikes_per_read):
        #     from_i, to_i = chunk_i*nspikes_per_read, (chunk_i+1)*nspikes_per_read
        for from_i in spike_table.index[::nspikes_per_read]:
            to_i = min(from_i + nspikes_per_read, spike_table.shape[0])
            waveforms = process_spike_chunk(spike_table.loc[from_i:to_i].copy(),
                                            sos_filter)
            # add the waveforms to the spike table
            spike_table.loc[from_i:to_i, waveforms.columns] = waveforms.values
            
            # if from_i > 1000:
            #     break
            
            sp_per_second = to_i /(time.time()-start_t)
            print(f"{to_i:07_d}/{spike_table.shape[0]:_} spikes, "
                    f"{(spike_table.shape[0]-to_i) /sp_per_second /60:.2f} "
                    f"minutes left at {sp_per_second:.2f} spikes/s", 
                    end='\r' if to_i < spike_table.shape[0] else 
                    f'\ntook {(time.time()-start_t)/60:.2f}min')
        return spike_table

    def calc_waveforms_infos(spikes, nsites):
        L.logger.debug(f"Calculating waveform infos for {spikes.cluster_id.nunique():,} clusters")
        def calc_wf_info(wf_df):
            channel_counts = {}
            # iterate over 1. 2. 3. bubble channel and count how often a pike occurs on there
            for chnl_str in chnls_str:
                wf_count = wf_df[chnl_str].value_counts().to_dict()
                # make keys strings
                wf_count = {f"{k}": v for k, v in wf_count.items()}
                channel_counts[f'{chnl_str}_wf_count'] = wf_count
            
            # make a flat list channl_ids and their waveforms
            all_chnls = wf_df[chnls_str].values.flatten()
            all_wfs = np.stack(wf_df[chnls_wfs_str].values.flatten())
            
            m, std = {}, {}
            # for each channel, no matter if 1. 2. or 3. in bubble, calculate the mean and std
            for chnl in np.unique(all_chnls):
                mask = all_chnls == chnl
                mean_wf = np.round(np.mean(all_wfs[mask], axis=0).astype(np.int16))
                std_wf = np.round(np.std(all_wfs[mask], axis=0).astype(np.int16))
                m[f"{chnl}"] = mean_wf
                std[f"{chnl}"] = std_wf

            avg_std_wf = {'averge_wf': m, 'std_wf': std}
            return channel_counts, avg_std_wf

        # set the bubble channel str column names
        chnls_str = ['channel', 'channel_2nd', 'channel_3rd'] if nsites == 3 else ['channel', 'channel_2nd']
        chnls_wfs_str = [f"{c}_hpf_wf" for c in chnls_str]
        
        cluster_infos = []
        for cluster_id, wf_df in spikes[['cluster_id', *chnls_str, *chnls_wfs_str]].groupby('cluster_id'):
            clst_chnl_counts, avg_std_wf = calc_wf_info(wf_df)
            cluster_infos.append(pd.Series({**clst_chnl_counts, **avg_std_wf, 
                                            **{'cluster_id': cluster_id,}}))
        return  pd.concat(cluster_infos, axis=1).T
    






    # ==========================================================================
    nas = device_paths()[0]
    session_name = os.path.basename(session_fullfname).replace(".hdf5", "")
    animal_name = session_name.split("_")[2]
    ss_info = pd.read_csv(os.path.join(nas, "devices", "animal_meta_info.csv"), 
                          index_col='animal_name')
    
    ss_dirnames = ss_info.loc[animal_name, 'ss_dirnames'].replace(" ", "").split(",")
    L.logger.debug(f"Found {len(ss_dirnames)} spike sorting runs/ batches.")
    traces, mapping = ml.session_modality_from_nas(session_fullfname, key='ephys_traces')
    if mapping is None:
        return None, None
    # print(f"Mapping:\n{mapping}")   

    ## spike sorting batches are compleltely seperate JRC runs/ directories, often split by region
    spike_aggr_over_ss_batches = []
    cluster_aggr_over_ss_batches = []
    for ss_i, ss_dirname in enumerate(ss_dirnames):
        ss_fulldir = os.path.join(nas, f"RUN_{animal_name}", "concatenated_ss", ss_dirname)
        L.logger.debug(f"Processing spikes from {ss_fulldir} for {session_name}")
        
        ss_session_lengths = pd.read_csv(os.path.join(ss_fulldir, "concat_session_lengths.csv"))
        ss_session_names = ss_session_lengths['name'].apply(lambda x: x[:x.find("min_")+3]).values
        L.logger.debug(f"Containes spike sorted sessions:\n{ss_session_names}")
        
        # unpack the concateated JRC output, going back to single session sample indices 
        entry_i = np.where(ss_session_names == session_name)[0]
        if len(entry_i) == 0:
            L.logger.warning(f"Session {session_name} not spike sorted in"
                             f" {os.path.basename(ss_fulldir)}")
            continue
        session_from_smple = ss_session_lengths.iloc[entry_i[0]-1].loc["nsamples_cum"] if entry_i[0] != 0 else 0
        session_to_smple = ss_session_lengths.iloc[entry_i[0]].loc["nsamples_cum"]
        
        ss_res_fullfname = os.path.join(ss_fulldir, 'concat_res.mat')
        if not os.path.exists(ss_res_fullfname):
            raise FileNotFoundError(f"Did not find _res.mat file in {ss_fulldir}")
        
        # get the cluster metadata
        cluster_table = ssbatch_cluster_metadata(ss_res_fullfname)
        cluster_aggr_over_ss_batches.append(cluster_table)
            
        # get the spikes
        spike_table, nsites = ssbatch_process_spikes(ss_res_fullfname, session_from_smple, 
                                                     session_to_smple)
        spike_aggr_over_ss_batches.append(spike_table)
        L.spacer("debug")
    
    # agggregate over batches and handle unique cluster ids
    sp_clust_metadata = aggr_spike_cluster_metadata(cluster_aggr_over_ss_batches)
    L.logger.debug(f"Aggregation over spike sorting groups:\n{sp_clust_metadata}")
    
    # aggregate spikes over batches, using the metadata to assign unique cluster ids
    spikes = aggr_spikes(spike_aggr_over_ss_batches, sp_clust_metadata)
    L.logger.debug(f"Aggregated spikes:\n{spikes}")
    # extract waveforms from raw traces.dat and insert into spikes dataframe
    spikes = extract_waveforms(spikes, nsites)
    
    # cluster metadata with session spike counts, and avg waveforms
    nspikes = spikes.cluster_id.value_counts().reindex(sp_clust_metadata.cluster_id, fill_value=0)
    sp_clust_metadata['session_spike_count'] = nspikes.values
    # use exteracted waveforms to calculate waveform infos, like average and std, channel wise
    waveform_infos = calc_waveforms_infos(spikes, nsites)
    sp_clust_metadata = pd.merge(sp_clust_metadata, waveform_infos, on='cluster_id', 
                                 how='left')
    return sp_clust_metadata, spikes








































def get_FiringRate40msHz(spikes, all_cluster_names):
    # create a timer interval calmun from sample_id
    bin_size_us = 40_000 # in us
    breaks = np.arange(0, spikes['ephys_timestamp'].max()+bin_size_us, 
                       bin_size_us, dtype='uint64')
    spikes['bin_40ms'] = pd.cut(
        spikes['ephys_timestamp'],
        bins=pd.IntervalIndex.from_breaks(breaks)
    )
    
    # then group by clusterID and use the bin_40ms to count spikes
    cnt = lambda x: x['bin_40ms'].value_counts() * 25 # 25 Hz = 1/40ms
    fr_40ms_hz = spikes.groupby('cluster_id_str').apply(cnt, include_groups=False)
    fr_40ms_hz = fr_40ms_hz.unstack().fillna(0).T
    # reindex to all cluster_ids across sessions
    fr_40ms_hz = fr_40ms_hz.reindex(all_cluster_names.iloc[:,0].values, fill_value=0, axis=1)
    
    # append the bin edges    
    fr_40ms_hz['from_ephys_timestamp'] = breaks[:-1]
    fr_40ms_hz['to_ephys_timestamp'] = breaks[1:]
    
    return fr_40ms_hz.reset_index(drop=True)

def get_FiringRate40msZ(fr_hz):
    def zscore(x):
        if not x.name.startswith('Unit'):
            return x
        if (x == 0).all():
            x.iloc[-1] = 25 # artifical single spike in last time bin to calc std
        z = ((x - x.mean()) / x.std())
        # last row is invalid because of artifical spike in last time bin, fill with previous bin
        # z.iloc[-1] = z.iloc[-2]
        return z
    return fr_hz.apply(zscore, axis=0)

# compute_primitives.py import as comp_prim
def run_pca(Z, skip_projection=False):
    corr_matrix = np.corrcoef(Z)
    eigenvals, eigenvecs = np.linalg.eigh(corr_matrix)
        
    # Sort eigenvalues in descending order
    idx = np.argsort(eigenvals)[::-1]
    eigenvals = eigenvals[idx]
    eigenvecs = eigenvecs[:, idx]
    
    eigenval_sum = np.sum(eigenvals)
    expl_var = eigenvals / eigenval_sum
    
    # # calculate projection of the data onto the eigenvectors
    if not skip_projection:
        Z_proj =  eigenvecs @ Z
        Z_proj = pd.DataFrame(Z_proj.T, # index=Z.index,
                              columns=[f"PC{i+1}" for i in range(Z_proj.shape[0])])
    else:
        Z_proj = None
        
    PCs = pd.DataFrame(eigenvecs, columns=[f"PC{i+1}" for i in range(eigenvecs.shape[1])])
    PCs = pd.concat([PCs, pd.Series(eigenvals, name='eigenvalues')], axis=1)
    PCs = pd.concat([PCs, pd.Series(expl_var, name='explained_variance')], axis=1)
    return PCs, Z_proj
    
def get_sessionPCA(fr_z):
    fr_z = fr_z.groupby(level='session_id').apply(lambda x: x.fillna(x.min().min()))
    fr_z = fr_z.set_index(["from_ephys_timestamp","to_ephys_timestamp"], append=True)
    fr_z.reset_index(level=(0,1,2,4), inplace=True, drop=True)
    
    # lst = fr_z.iloc[-1] 
    # fr_z = fr_z.iloc[:25*16*5]
    # fr_z.iloc[-1] = 0.0001
    
    print(f"Firing rate shape: {fr_z.shape}")
    Z = fr_z.values.T  # transpose to have neurons in rows, time bins in columns
    
    # PCs, Z_proj = comp_prim.run_pca(Z)
    PCs, Z_proj = run_pca(Z)
    
    PCs['cluster_id_str'] = fr_z.columns.values
    Z_proj['from_ephys_timestamp'] = fr_z.index.get_level_values('from_ephys_timestamp')
    Z_proj['to_ephys_timestamp'] = fr_z.index.get_level_values('to_ephys_timestamp')
    return PCs, Z_proj




def get_SessionPCs40msCAs(PCs):
    angle_aggr = []
    # Use distinct variable names for the two session comparisons
    session_ids = PCs.index.unique(level='session_id')
    Logger().logger.debug(f"Calculating canonical angles between "
                          f"{len(session_ids)} session PC spaces...")
    for from_s_id in session_ids:
        # Get the PCs for the "from" session and keep only numeric PC columns
        from_session_pc = PCs.xs(from_s_id, level='session_id')
        # we align the subspace of the n components that explain 80% of the variance
        from_session_nPCs = (from_session_pc.explained_variance.cumsum()<.8).sum()
        from_s_subspace = from_session_pc.filter(regex='^PC').values[:, :from_session_nPCs]
        
        for to_s_id in session_ids:
            # Get the PCs for the "to" session
            to_session_pc = PCs.xs(to_s_id, level='session_id')
            to_session_nPCs = (to_session_pc.explained_variance.cumsum()<.8).sum()
            to_s_subspace = to_session_pc.filter(regex='^PC').values[:, :to_session_nPCs]
            # print(f"Comparing S{from_s_id}({from_session_nPCs}): to S{to_s_id}({to_session_nPCs})")
            
            # Compute SVD between matching subspaces
            M = from_s_subspace.T @ to_s_subspace
            from_s_c, S, to_s_comp_h_c = np.linalg.svd(M)
            canonc_angles = np.arccos(np.clip(S, -1, 1))
            canonc_angles = np.round(np.rad2deg(canonc_angles), 2)
            angle_aggr.append(pd.Series(canonc_angles, name=(from_s_id, to_s_id),
                                        index=[f"CA{ca}" for ca in range(canonc_angles.shape[0])],
                                        ))
    angle_aggr = pd.concat(angle_aggr, axis=1).T
    angle_aggr.index.names = ['from_session_id', 'to_session_id']
    return angle_aggr.reset_index()

def get_Ensamble40msProjEncodings(ensemble_proj, kinematics, kinematic_vars=None, verbose=True):
    """
    For each ensemble, fit a linear regression to predict its activity from each kinematic variable.
    Returns a DataFrame with R² scores for each ensemble/kinematic pair.
    
    ensemble_proj: DataFrame, index should be IntervalIndex (time bins), columns are ensemble names
    kinematics: DataFrame, indexed by 'frame_ephys_timestamp'
    kinematic_vars: list of str, which kinematic columns to use (default: all except index)
    verbose: bool, print R² > 0.03
    
    Returns: DataFrame (rows: ensemble, columns: kinematic variable, values: R²)
    """
    # Map kinematics to ensemble time bins
    if not isinstance(ensemble_proj.index, pd.IntervalIndex):
        raise ValueError("ensemble_proj must have IntervalIndex as index (time bins).")
    # Assign each kinematics row to a bin
    kinematics = kinematics.copy()
    kinematics['ephys_bin'] = ensemble_proj.index.get_indexer(kinematics.index)
    kinematics_grouped = kinematics.groupby('ephys_bin').mean().round(3)
    # Only keep bins that exist in ensemble_proj
    kinematics_grouped = kinematics_grouped.loc[kinematics_grouped.index >= 0]
    # Optionally select kinematic variables
    if kinematic_vars is None:
        kinematic_vars = [col for col in kinematics_grouped.columns if col.startswith('frame_')]
    # Prepare result DataFrame
    r2_results = pd.DataFrame(index=ensemble_proj.columns, columns=kinematic_vars, dtype=float)
    model = LinearRegression()
    # For each ensemble
    for ens in ensemble_proj.columns:
        y = ensemble_proj[ens].iloc[kinematics_grouped.index]
        for regre in kinematic_vars:
            x = kinematics_grouped[regre]
            # Fit regression
            model.fit(x.values.reshape(-1, 1), y.values.reshape(-1, 1))
            r2 = model.score(x.values.reshape(-1, 1), y.values.reshape(-1, 1))
            r2_results.loc[ens, regre] = r2
            if verbose and r2 > 0.03:
                print(f"Ensemble {ens} - {regre} R^2: {r2:.3f}")
    return r2_results

def get_ConcatenatedPCA40ms(fr_z):
    # fill 0 firing rate neurons with the minimum firing rate of the session (0 Hz)
    fr_z = fr_z.groupby(level='session_id').apply(lambda x: x.fillna(x.min().min()))
    fr_z = fr_z.set_index(["from_ephys_timestamp","to_ephys_timestamp"], append=True)
    fr_z.reset_index(level=(0,1,2,4), inplace=True, drop=True)
    print(f"Firing rate shape: {fr_z}")
    
    Z = fr_z.values.T  # transpose to have neurons in rows, time bins in columns
    
    corr_matrix = np.corrcoef(Z)
    eigenvals, eigenvecs = np.linalg.eigh(corr_matrix)
        
    # Sort eigenvalues in descending order
    idx = np.argsort(eigenvals)[::-1]
    eigenvals = eigenvals[idx]
    eigenvecs = eigenvecs[:, idx]

    eigenval_sum = np.sum(eigenvals)
    expl_var = eigenvals / eigenval_sum
    
    # # calculate projection of the data onto the eigenvectors
    # Z_pca =  eigenvecs @ Z
    # PC_embeddings = pd.DataFrame(Z_pca.T, index=fr_z.index,
    #                              columns=[f"PC{i+1}" for i in range(Z_pca.shape[0])])
    # print(PC_embeddings)
    
    PCs = pd.DataFrame(eigenvecs, columns=[f"PC{i+1}" for i in range(eigenvecs.shape[1])])
    PCs = pd.concat([PCs, pd.Series(eigenvals, name='eigenvalues')], axis=1)
    PCs = pd.concat([PCs, pd.Series(expl_var, name='explained_variance')], axis=1)
    return PCs

from numba import jit, prange

@jit(nopython=True, parallel=True)
def _compute_assembly_activity_numba(assembly_templates, fr_data):
    n_assemblies, n_bins, n_neurons = assembly_templates.shape[1], fr_data.shape[0], fr_data.shape[1]
    assembly_activity = np.zeros((n_assemblies, n_bins))
    
    # Ensure contiguous arrays for better performance
    assembly_templates = np.ascontiguousarray(assembly_templates)
    fr_data = np.ascontiguousarray(fr_data)
    
    for assembly_idx in prange(n_assemblies):
        template = assembly_templates[:, assembly_idx].copy()  # Make contiguous copy
        projector = np.outer(template, template)
        np.fill_diagonal(projector, 0.0)
        
        # Make projector contiguous
        projector = np.ascontiguousarray(projector)
        
        for t in range(n_bins):
            spike_vector = fr_data[t, :].copy()  # Make contiguous copy
            assembly_activity[assembly_idx, t] = spike_vector.T @ projector @ spike_vector
    
    return assembly_activity

def get_ConcatenatedEnsambles40ms(PCs, all_fr_z):
    eigenvalues = PCs.pop('eigenvalues')
    explained_variance = PCs.pop('explained_variance')
    print(PCs)
    
    from_ephys_timestamp = all_fr_z.pop('from_ephys_timestamp',)
    to_ephys_timestamp = all_fr_z.pop('to_ephys_timestamp',)
    session_id = all_fr_z.index.get_level_values('session_id')
    all_fr_z = all_fr_z.groupby(level='session_id').apply(lambda x: x.fillna(x.min().min()))
    print(all_fr_z)
    
    n_bins = all_fr_z.shape[0]
    n_neurons = PCs.shape[0]
    # Determine statistical threshold
    q = n_bins / n_neurons
    # Using Marcenko-Pastur distribution for threshold
    lambda_max = (1 + np.sqrt(1/q))**2
    
    # Count significant assemblies
    n_assemblies = np.sum(eigenvalues > lambda_max)
    print(f"Number of assemblies detected: {n_assemblies}")
    
    # Use FastICA on z-scored data to find assemblies
    print(f"Calculating assembly templates using FastICA with {n_assemblies} components...")
    ica = FastICA(n_components=n_assemblies, random_state=42, max_iter=500)
    ica.fit(all_fr_z@PCs.values[:, :n_assemblies])  # ICA expects samples x features
    assembly_templates = PCs.values[:, :n_assemblies]@ica.components_  # Transpose to neurons x assemblies
    
    print(f"Computing assembly activity for {n_assemblies} assemblies using JIT...")    
    assembly_activity = _compute_assembly_activity_numba(assembly_templates, all_fr_z.values)

    
    assembly_templates = pd.DataFrame(assembly_templates, index=PCs.index,
                                    columns=[f"Assembly{i+1:03d}" for i in range(n_assemblies)])
    
    idx = pd.MultiIndex.from_arrays([session_id,from_ephys_timestamp, to_ephys_timestamp],
                                    names=['session_id', 'from_ephys_timestamp', 'to_ephys_timestamp'])
    assembly_activity = pd.DataFrame(assembly_activity.T,
                                     columns=[f"Assembly{i+1:03d}" for i in range(n_assemblies)],
                                     index=idx)
    return assembly_templates, assembly_activity.reset_index()


# def get_FiringRateTrackbinsHz(fr_z, track_behavior_data):
    
#     def trackwise_averages(fr, track_behavior_data):
#         def time_bin_avg(trial_data, ):
#             print(f"{trial_data.from_z_position_bin.iloc[0]:04}", end='\r')
#             trial_aggr = []
#             for row in range(trial_data.shape[0]):
#                 from_t, to_t = trial_data.iloc[row].loc[['posbin_from_ephys_timestamp', 'posbin_to_ephys_timestamp']]
#                 from_t = from_t - 40_000
#                 to_t = to_t + 40_000
                
#                 trial_d_track_bin_fr = fr.loc[(fr.index.left > from_t) & (fr.index.right < to_t)]
#                 # print(trial_data.iloc[row])
#                 # print(trial_d_track_bin_fr.shape, to_t-from_t, )
#                 # print()
#                 trial_aggr.append(trial_d_track_bin_fr.values)
#             trial_aggr_concat = np.concatenate(trial_aggr, axis=0)
#             if trial_aggr_concat.shape[0] == 0:
#                 # no trials in this bin
#                 return pd.Series(np.nan, index=fr.columns)
#             m = trial_aggr_concat.mean(axis=0)
#             return pd.Series(m, index=fr.columns)
                
#         print("Track bin: ")
#         return track_behavior_data.groupby('from_z_position_bin', ).apply(time_bin_avg)
    
#     # recover index
#     old_idx = fr_z.index
#     fr_z = fr_z.reset_index(drop=True)
#     new_idx = pd.IntervalIndex.from_breaks(
#         np.arange(0, fr_z.shape[0]*40_000+1, 40_000, dtype='uint64'),
#     )
#     fr_z.index = new_idx
#     fr_hz_averages = trackwise_averages(fr_z, track_behavior_data)
#     return fr_hz_averages
#     import matplotlib.pyplot as plt
#     plt.imshow(fr_hz_averages.values.T, aspect='auto', interpolation='nearest')
#     plt.colorbar()
#     plt.show()
#     print(fr_hz_averages)

def get_FiringRateTrackwiseHz(fr, track_behavior_data):
    def time_bin_avg(posbin_data, ):
        # cue = posbin_data.cue.iloc[0]
        # trial_outcome = posbin_data.trial_outcome.iloc[0]
        pos_bin = posbin_data.from_position_bin.iloc[0]
        print(f"{pos_bin:04}", end='\r')
        trial_aggr = []
        # print("--------------------")
        # print(f"{pos_bin=}, trial_id:")
        # print(posbin_data.trial_id)
        # print(posbin_data)
        
        
        # for tr_id in posbin_data.trial_id:
        #     trial_data = posbin_data.loc[posbin_data.trial_id==tr_id]
        #     from_t, to_t = trial_data.loc[:, ['posbin_from_ephys_timestamp', 'posbin_to_ephys_timestamp']].values[0]
        #     from_t = from_t - 40_000
        #     to_t = to_t + 40_000
            
        #     # print(from_t, to_t)
        #     # print(fr)
        #     trial_d_track_bin_fr = fr.loc[(fr.index.left > from_t) & (fr.index.right < to_t)]
        #     m = trial_d_track_bin_fr.mean(axis=0)
        #     trial_aggr.append(pd.Series(m, index=fr.columns, name=(pos_bin,tr_id,cue,trial_outcome)))
        
        
        # to_posbin_t = trial_data.posbin_from_ephys_timestamp
        from_posbin_t = posbin_data.posbin_from_ephys_timestamp.values
        to_posbin_t = posbin_data.posbin_to_ephys_timestamp.values
        interval = pd.IntervalIndex.from_arrays(
            from_posbin_t-40_000,
            to_posbin_t+40_000,
            closed='both',
        )
        # print(interval)
        # print(fr.index.mid)
        assigned_bin = pd.cut(fr.index.mid,
                              bins=interval,
                              labels=posbin_data.trial_id[:-1],
        )
        trials_exist_mask = (assigned_bin.value_counts() != 0).values
        # print(f"Trials exist mask sum: {trials_exist_mask.sum()}")
        
        # slice out the 40ms fr bins that overlap with the trial-wise position bin
        trial_fr = fr[assigned_bin.notna()].copy().astype(np.float32)
        # add a column indicating the 
        trial_fr['posbin_t_edges'] = assigned_bin[assigned_bin.notna()]
        # print(trial_fr.shape)
        posbin_trial_wise_fr = trial_fr.groupby('posbin_t_edges', observed=True).mean()
        # print(posbin_trial_wise_fr.shape)
        posbin_trial_wise_fr /= interval.length.values[trials_exist_mask, None] /1e6 # us to s
        # print(posbin_trial_wise_fr.shape)

        # add meta data, cue outcome, position bin, trial id        
        posbin_trial_wise_fr['cue'] = posbin_data[trials_exist_mask].cue.values
        posbin_trial_wise_fr['trial_outcome'] = posbin_data[trials_exist_mask].trial_outcome.values
        posbin_trial_wise_fr['choice_R1'] = posbin_data[trials_exist_mask].choice_R1.values
        posbin_trial_wise_fr['choice_R2'] = posbin_data[trials_exist_mask].choice_R2.values
        posbin_trial_wise_fr['bin_length'] = interval.length.values[trials_exist_mask]/1e6
        posbin_trial_wise_fr.index = posbin_data.trial_id.values[trials_exist_mask]
        # print(posbin_trial_wise_fr)
        # print("---")
        # exit()
        return posbin_trial_wise_fr        

    # recover interval index
    fr.index = pd.IntervalIndex.from_arrays(fr.pop("from_ephys_timestamp"), 
                                            fr.pop("to_ephys_timestamp"))

    print("Track bin: ")
    fr_hz_averages = track_behavior_data.groupby(['from_position_bin']).apply(time_bin_avg)
    fr_hz_averages.index = fr_hz_averages.index.rename(['from_position_bin', 'trial_id'],)
    fr_hz_averages.reset_index(inplace=True, drop=False)
    # print(fr_hz_averages)
    # exit()
    return fr_hz_averages

def get_PCsZonewise(fr, track_behavior_data):
    L = Logger()
    PCs_var_explained = .8
    fr = fr.set_index(['trial_id', 'from_position_bin', 'cue', 'trial_outcome', 
                       'choice_R1', 'choice_R2'], append=True, )
    fr.index = fr.index.droplevel(3) # entry_id

    fr.drop(columns=['bin_length', ], inplace=True)
    fr.columns = fr.columns.astype(int)
    fr = fr.reindex(columns=sorted(fr.columns))
    
    track_behavior_data = track_behavior_data.set_index(['trial_id', 'from_position_bin', 'cue', 'trial_outcome', 
                                       'choice_R1', 'choice_R2'], append=True, )
    track_behavior_data.index = track_behavior_data.index.droplevel(3) # entry_id
    
    zones = {
        'beforeCueZone': (-168, -100),
        'cueZone': (-80, 25),
        'afterCueZone': (25, 50),
        'reward1Zone': (50, 110),
        'betweenRewardsZone': (110, 170),
        'reward2Zone': (170, 230),
        'postRewardZone': (230, 260),
        'wholeTrack': (-168, 260),
    }
    
    aggr_embeds = []
    aggr_subspace_basis = []

    #TODO each sessions has differnt number of neurons
    fr = fr.reindex(np.arange(1,78), axis=1).fillna(0)

    for i in range(4):
        # which modality to use for prediction
        if i == 0:
            predictor = fr.iloc[:, :20]
            predictor_name = 'HP'
        elif i == 1:   
            predictor = fr.iloc[:, 20:]
            predictor_name = 'mPFC'
        elif i == 2:
            predictor = track_behavior_data.loc[:, ['posbin_velocity', 'posbin_acceleration', 'lick_count',
                                           'posbin_raw', 'posbin_yaw', 'posbin_pitch']]
            predictor_name = 'behavior'
        elif i == 3:
            predictor = fr.iloc[:]
            predictor_name = 'HP-mPFC'
            
        debug_msg = (f"Embedding {predictor_name} with PCA:\n")
        for zone, (from_z, to_z) in zones.items():
            zone_data = predictor.loc[pd.IndexSlice[:,:,:,:,np.arange(from_z,to_z)]].astype(float)
            
            # Standardize features
            scaler = StandardScaler()
            zone_data.loc[:,:] = scaler.fit_transform(zone_data)
             
            zone_data_Z_trialwise = zone_data.unstack(level='from_position_bin')
            zone_data_Z_trialwise.index = zone_data_Z_trialwise.index.droplevel([0,1,2])
            zone_data_Z_trialwise = zone_data_Z_trialwise.fillna(0).astype(float)
            
            pca = PCA(n_components=PCs_var_explained)
            embedded = pca.fit_transform(zone_data_Z_trialwise)
            
            debug_msg += (f"{embedded.shape[1]:3d} PCs capture {pca.explained_variance_ratio_.sum():.2f} "
                          f" of variance of {zone_data_Z_trialwise.shape[1]:5d} "
                          f"input dims in {embedded.shape[0]:3d} trials at "
                          f"{zone} ({from_z}, {to_z})\n")

            embedded = np.round(embedded, 3)
            aggr_embeds.append(pd.Series(embedded.tolist(), index=zone_data_Z_trialwise.index,
                                         name=(zone, predictor_name)))
            
            columns = pd.MultiIndex.from_product([[zone], [predictor_name], 
                                                  np.arange(embedded.shape[1])])
            aggr_subspace_basis.append(pd.DataFrame(pca.components_.round(3).T,
                                                    columns=columns))
        L.logger.debug(debug_msg)

    aggr_embeds = pd.concat(aggr_embeds, axis=1).stack(level=0, future_stack=True)
    aggr_embeds.reset_index(inplace=True, drop=False)
    aggr_embeds.rename(columns={"level_5": "track_zone"}, inplace=True)
    
    # the subspace basis is a 2D array with pricipal components as columns, rows
    # indicate predictors and track zones
    #TODO warning right now due to old stacking behavior, will be fixed in future
    aggr_subspace_basis = pd.concat(aggr_subspace_basis, axis=0).stack(level=(0,1), future_stack=False)
    aggr_subspace_basis.reset_index(inplace=True, drop=False)
    aggr_subspace_basis.rename(columns={"level_1": "track_zone",
                                        "level_2": "predictor_name",}, inplace=True)
    aggr_subspace_basis.drop(columns='level_0', inplace=True)
    
    # check for in proper sessions that lack spikes for most of the session
    valid_ephys_mask = aggr_embeds['mPFC'].notna()
    valid_beh_mask = aggr_embeds['behavior'].notna()
    if not all(valid_ephys_mask == valid_beh_mask):
        msg = (f"Ephys and behavior trials mismatch!\n"
               f"Valid trials in ephys: {aggr_embeds.trial_id[valid_ephys_mask].unique()}, "
               f"valid trials in behavior: {aggr_embeds.trial_id[valid_beh_mask].unique()} "
               f"Using common set of trials")
        Logger().logger.warning(msg)
        aggr_embeds.dropna(how='any', inplace=True)
    
    return aggr_subspace_basis, aggr_embeds

def get_PCsSubspaceAngles(session_subspace_basis, all_subspace_basis):
    session_subspace_basis.index = session_subspace_basis.index.droplevel((0,1))  # Drop the first level of the index if it exists
    session_subspace_basis.set_index(["track_zone", 'predictor_name'], inplace=True, append=True)
    session_subspace_basis.index = session_subspace_basis.index.droplevel("entry_id")  # Drop the entry_id level if it exists
    
    all_subspace_basis.index = all_subspace_basis.index.droplevel((0,1))  # Drop the first level of the index if it exists
    all_subspace_basis.set_index(["track_zone", 'predictor_name'], inplace=True, append=True)
    all_subspace_basis.index = all_subspace_basis.index.droplevel("entry_id")  # Drop the entry_id level if it exists
    # print(all_subspace_basis)
    
    angle_aggr = []
    comps_aggr = []
    for zone in all_subspace_basis.index.unique(level='track_zone'):
        print(zone, end='\r')
        for predictor in all_subspace_basis.index.unique(level='predictor_name'):
            # get the subspace basis for the session
            # track_session_subspace = session_subspace_basis.loc[(zone, predictor), :]
            # get the subspace basis for all sessions
            zone_all_subspace = all_subspace_basis.loc[(slice(None),zone, predictor), :]
            session_n_PCs = zone_all_subspace.groupby(level='session_id').apply(
                                                       lambda x: x.notna().all(0).sum())
            # some sessions have very low number of PCs, exclude those, will be NaN in the end
            std = np.std(session_n_PCs.values)
            cutoff = np.mean(session_n_PCs.values) - 2*std
            
            too_few_PCs_mask = session_n_PCs < cutoff
            n_PCs = session_n_PCs[~too_few_PCs_mask].min()
            
            # # print(track_all_subspace)
            # print(zone, predictor,)
            # smth = session_n_PCs.to_frame(name='n_PCs').copy()
            # smth['keep'] = smth.n_PCs > cutoff
            # print(smth)
            # print('-----')
            
            # print(zone, predictor,)
            # print(n_PCs)
            # n_PCs = 200
            
            # zone_all_subspace = zone_all_subspace.iloc[:, :n_PCs]
            # zone_session_subspace = , :].iloc[:, :n_PCs]
            
            # print(zone_all_subspace, zone_session_subspace)
            s0_subspace = session_subspace_basis.loc[(slice(None), zone, predictor)].values[:, :n_PCs]
            if np.isnan(s0_subspace[:, :n_PCs]).any() or s0_subspace.shape[1] < n_PCs:
                Logger().logger.warning(f"Session subspace has too few PCs for {zone} {predictor}.")
                continue
            
            for s_id in session_n_PCs[~too_few_PCs_mask].index:
                s_compare_subspace = zone_all_subspace.loc[s_id, :].values[:, :n_PCs]
                # print(zone_all_subspace.loc[s_id, :])
                
                # print(s0_subspace, s_compare_subspace)
                # print(s0_subspace.shape, s_compare_subspace.shape)
                
                # print("--")
                M = s0_subspace.T @ s_compare_subspace
                s0_c, S, s_comp_h_c = np.linalg.svd(M)
                

                canonc_angles = np.arccos(np.clip(S, -1, 1))
                s0_c_subspace = (s0_subspace @ s0_c).astype(np.float16)
                # print(s0_c_subspace)
                # print(s0_c_subspace.shape)
                # CC_U = (s1_PCs_U @ U_c[:, :])
                # print(c1_U)
                # print(c1_U.shape)
                
                # canonc_angles = subspace_angles(s0_subspace[:, :n_PCs],
                #                                 s_compare_subspace[:, :n_PCs])
                # canonc_angles = np.rad2deg(canonc_angles)
                # print(canonc_angles)
                
                angle_aggr.append(pd.Series(canonc_angles, index=np.arange(n_PCs),
                                            name=(zone, predictor, s_id)))
                comps_aggr.append(pd.DataFrame(s0_c_subspace, columns=pd.MultiIndex.from_product(
                                                 [[zone], [predictor], [s_id], np.arange(n_PCs)],
                                                 names=['track_zone', 'predictor', 'comp_session_id', 'CC_i'],
                                             )))
                
                
                print(angle_aggr[-1])
    if len(angle_aggr) == 0:
        return None
    
    angle_aggr = pd.concat(angle_aggr, axis=1).T
    angle_aggr.index.names = ['track_zone', 'predictor', 'comp_session_id']
    
    comps_aggr = pd.concat(comps_aggr, axis=1)
    comps_aggr = comps_aggr.T
    return comps_aggr.reset_index(), angle_aggr.reset_index()
            
def get_SVMCueOutcomeChoicePred(PCsZoneEmbeddings):
    L = Logger()
    print(PCsZoneEmbeddings)

    def fit_SVMs_with_bootstrap(X, Ys, name, n_iterations=200):
        predictions = []
        rng = np.random.default_rng(42)

        for Y_name, y in Ys.items():
            # if Y_name != 'choice_R1':
            #     continue
            lbl_counts = pd.Series(y).value_counts()
            print(Y_name)
            if lbl_counts.min() < 5 or len(lbl_counts) < 2:
                L.logger.warning(f"Not enough samples for {Y_name} in {name}: ({lbl_counts})")
                continue
            elif len(lbl_counts) != 2:
                L.logger.warning(f"More than 2 classes for {Y_name} in {name}: ({lbl_counts})")
                continue

            for kernel in ('linear', 'rbf'):
                # if kernel != 'linear':
                #     continue
                Cs = [0.1, .5, 1, 5, 10,]
                accs, f1s = [], []

                aggr_predictions = np.ones((n_iterations, len(X)), dtype=int) * -1
                print(aggr_predictions.shape)
                for i in range(n_iterations):
                    indices = rng.choice(len(X), size=len(X), replace=True)
                    X_boot, y_boot = X[indices], y[indices]
                    # only a single cclass check:
                    if len(np.unique(y_boot)) < 2:
                        print("Skipping SVM fit due to single class in bootstrap sample")
                        continue
                    oob_mask = np.ones(len(X), dtype=bool)
                    oob_mask[indices] = False
                    X_oob, y_oob = X[oob_mask], y[oob_mask]

                    if len(y_oob) < 5 or len(np.unique(y_oob)) < 2:
                        continue

                    pipeline = Pipeline([
                        ('scaler', StandardScaler()),
                        ('svc', SVC(kernel=kernel, gamma='scale'))
                    ])
                    grid_search = GridSearchCV(
                        estimator=pipeline,
                        param_grid={'svc__C': Cs},
                        cv=6,
                        scoring='balanced_accuracy',
                        n_jobs=-1,
                        verbose=False,
                    )
                    grid_search.fit(X_boot, y_boot)
                    y_pred = grid_search.predict(X_oob)
                    report = classification_report(y_oob, y_pred, output_dict=True, zero_division=0)

                    accs.append(balanced_accuracy_score(y_oob, y_pred))
                    f1s.append(report['macro avg']['f1-score'])
                    
                    # every row is one bootstrap iteration
                    aggr_predictions[i, oob_mask] = y_pred
                
                # get the "average" prediction across bootstrap iterations
                aggr_predictions = pd.DataFrame(aggr_predictions)
                aggr_predictions[aggr_predictions == -1] = np.nan
                pred = aggr_predictions.mode(axis=0).iloc[0].values
                
                # difference
                f1_aggr = classification_report(y, pred, output_dict=True, zero_division=0)['macro avg']['f1-score']
                
                print(f"mean: {np.mean(f1s):.3f}, aggr: {f1_aggr:.3f}, "
                      f"diff: {np.mean(f1s) - f1_aggr:.3f}")
                
                # # Fit final model on full data for predictions
                # final_model = GridSearchCV(
                #     estimator=Pipeline([
                #         ('scaler', StandardScaler()),
                #         ('svc', SVC(kernel=kernel, gamma='scale'))
                #     ]),
                #     param_grid={'svc__C': Cs},
                #     cv=6,
                #     scoring='f1_macro',
                #     n_jobs=-1
                # )
                # final_model.fit(X, y)
                # pred = final_model.predict(X)
                # # print(np.stack((y, pred)).T)
                
                # print(f"---\n{Y_name} {name} {kernel}")
                # if Y_name == 'cue' and kernel == 'linear' and name[1] == 'afterCueZone' and name[0] == 'HP':
                #     print(f"---\n{Y_name} {name} {kernel}")
                #     print(classification_report(y_oob, y_pred))
                #     print(pred)
                #     print(y)
                #     # exit()
                
 
                col_index = pd.MultiIndex.from_tuples([(*list(name), kernel, Y_name, n) for n in 
                                                    ('y', 'y_true', 'n_PCs', 'acc', 'acc_std', 'f1')],
                                                    names=['predictor', 'track_zone', 'model', 'predicting', 'output'])
                pred_output = np.concatenate([
                    pred[:, None], y[:, None],
                    np.tile(np.array([X.shape[1], np.mean(accs), np.std(accs), np.mean(f1s)]), (len(pred), 1))
                ], axis=1)

                predictions.append(pd.DataFrame(pred_output, columns=col_index, index=PCsZoneEmbeddings.index))
        if predictions == []:
            L.logger.warning(f"None enough trials to fit any SVM for {name}")
            return None
        return pd.concat(predictions, axis=1)
    


    
    
    

    # fix seed
    np.random.seed(42)

    def parse_string_to_array(x):
        # TODO why?
        if isinstance(x, np.ndarray):
            return x
        if pd.isna(x):
            return x
        return np.fromstring(x.strip("[]"), sep=", ", dtype=np.float32)
    
    PCsZoneEmbeddings = PCsZoneEmbeddings.set_index(['track_zone', 'trial_id', 'trial_outcome', 
                                         'cue', 'choice_R1', 'choice_R2'], 
                                        append=False).unstack(level='track_zone')
    all_zones = []
    for column in PCsZoneEmbeddings.columns:
        # if column[1] != 'beforeCueZone':
        #     continue
        # if column[0] in ('HP', 'mPFC'):
        #     continue
        X_list = PCsZoneEmbeddings[column].apply(parse_string_to_array)
        if X_list.isna().any():
            L.logger.warning(f"Missing trials for {column}...")
            mask = X_list.isna()
        else:
            mask = np.ones(X_list.shape, dtype=bool)
        X = np.stack(X_list[mask].values)
            
        if X.shape[0] <8:
            Logger().logger.warning(f"Minimum of 8 trials req. to fit SVM. "
                                    f"{X.shape[0]} trials found for {column}")
            continue
        Logger().logger.debug(f"Fitting SVM with {column}...")
        # print(PCsZoneEmbeddings)
        Y_cue = PCsZoneEmbeddings[mask].index.get_level_values('cue').values
        Y_outcome = PCsZoneEmbeddings[mask].index.get_level_values('trial_outcome').values
        Y_outcome = Y_outcome.astype(bool).astype(int)
        # TODO: add choice
        Y_choice_R1 = PCsZoneEmbeddings[mask].index.get_level_values('choice_R1').values.astype(int)
        Y_choice_R2 = PCsZoneEmbeddings[mask].index.get_level_values('choice_R2').values.astype(int)
        
        predictions = fit_SVMs_with_bootstrap(X, Ys={'cue':Y_cue, 'outcome':Y_outcome, 'choice_R1':Y_choice_R1, 'choice_R2': Y_choice_R2}, name=column)
        all_zones.append(predictions)

    if all_zones == [] or all(pr is None for pr in all_zones):
        L.logger.warning("None of zones in the session have min. trials == 6")
        return None
    
    all_zones = pd.concat(all_zones, axis=1)
    all_zones = all_zones.stack(level=('predictor', 'track_zone', 'model', 'predicting'), future_stack=True).reset_index()
    # print(all_zones.columns)
    # print(all_zones)
    return all_zones

def get_PVCueCorr(trackfr_data, track_behavior_data):
    def compute_population_vector_correlation(PVs):
        # Split the data into cue 1 and cue 2
        pv1 = PVs.xs(1, level='cue')
        pv2 = PVs.xs(2, level='cue')
        unif_index = pv1.index.intersection(pv2.index)
        pv1 = pv1.loc[unif_index]
        pv2 = pv2.loc[unif_index]
        
        spatial_avg_pv1 = []
        spatial_avg_pv2 = []
        for i in range(0, len(unif_index), 5):
            spatial_bins = unif_index[i:i+5]
            spatial_avg_pv1.append(pv1.loc[spatial_bins].mean(0).rename(spatial_bins[0]))
            # print(spatial_avg_pv1)
            spatial_avg_pv2.append(pv2.loc[spatial_bins].mean(0).rename(spatial_bins[0]))
            # print(spatial_avg_pv2)
            # exit()
            
        spatial_avg_pv1 = pd.concat(spatial_avg_pv1, axis=1).T
        spatial_avg_pv2 = pd.concat(spatial_avg_pv2, axis=1).T

        # Calculate correlation matrix for averaged bins
        corr_matrix = np.zeros((len(spatial_avg_pv1), len(spatial_avg_pv2)))
        for i, cue1_spatial_bin in enumerate(spatial_avg_pv1.index):
            x = spatial_avg_pv1.loc[cue1_spatial_bin]
            # print(x)
            for j, cue2_spatial_bin in enumerate(spatial_avg_pv2.index):
                y = spatial_avg_pv2.loc[cue2_spatial_bin]
                # corr_matrix[(cue1_spatial_bin, cue2_spatial_bin)] = np.corrcoef(x, y)[0, 1]
                corr_matrix[i, j] = np.corrcoef(x, y)[0, 1]
        return pd.DataFrame(corr_matrix, 
                            index=spatial_avg_pv1.index, 
                            columns=spatial_avg_pv2.index)
    
    L = Logger()
    # TODO subset into trial_outcome group and choice and trial 1/3 2/3 3/3
    trackfr_data = trackfr_data.set_index(['trial_id', 'from_position_bin', 'cue', 'trial_outcome', 
                                           'choice_R1', 'choice_R2'], append=True)
    trackfr_data.index = trackfr_data.index.droplevel((0,1,2,3))
    trackfr_data.drop(columns=['bin_length'], inplace=True)
    fr = trackfr_data.reindex(np.arange(1,78).astype(str), axis=1).fillna(0)
     
    track_behavior_data = track_behavior_data.set_index(['trial_id', 'from_position_bin', 
                                                         'cue', 'trial_outcome', 
                                       'choice_R1', 'choice_R2'], append=True, )
    track_behavior_data.index = track_behavior_data.index.droplevel(3) # entry_id
    
    PVCueCorr_aggr = []
    for i in range(4):
        # which modality to use for prediction
        if i == 0:
            predictor = fr.iloc[:, :20]
            predictor_name = 'HP'
        elif i == 1:   
            predictor = fr.iloc[:, 20:]
            predictor_name = 'mPFC'
        elif i == 2:
            predictor = track_behavior_data.loc[:, ['posbin_velocity', 'posbin_acceleration', 'lick_count',
                                                    'posbin_raw', 'posbin_yaw', 'posbin_pitch']]
            predictor_name = 'behavior'
        elif i == 3:
            predictor = fr.iloc[:]
            predictor_name = 'HP-mPFC'
            
        debug_msg = (f"Correlating population vector: {predictor_name}\n")
        
        # mean over trials
        PVs = predictor.groupby(level=('from_position_bin', 'cue')).mean()
        cross_corr = compute_population_vector_correlation(PVs)
        print(cross_corr)
        cross_corr['predictor'] = predictor_name
        cross_corr = cross_corr.reset_index().rename(columns={'index': 'cue1_from_position_bin'})
        PVCueCorr_aggr.append(cross_corr)
            
        # if i == 0:
        #     # import matplotlib.pyplot as plt
        #     plt.figure(figsize=(10, 8))
        #     print(cross_corr)
        #     print(cross_corr.cue1_from_position_bin)
        #     idx = cross_corr.pop('cue1_from_position_bin')
        #     cross_corr.pop('predictor')
        #     plt.imshow(cross_corr, aspect='auto', interpolation='nearest', vmin=.5, vmax=1)
        #     plt.colorbar(label='Correlation')
        #     plt.title("Population Vector Correlation (5-bin averages)")
        #     plt.xlabel("Position Bin (Cue 1)")
        #     plt.ylabel("Position Bin (Cue 2)")
            
        #     # Add tick labels for averaged bins
        #     tick_positions = np.arange(len(cross_corr))
        #     tick_labels = [f"{x:.0f}" for x in idx]
        #     plt.xticks(tick_positions[::2], tick_labels[::2], rotation=45)
        #     plt.yticks(tick_positions[::2], tick_labels[::2])
            
        #     plt.tight_layout()
        #     plt.savefig("population_vector_correlation.png", dpi=300, bbox_inches='tight')
            # exit()
    PVCueCorr_aggr = pd.concat(PVCueCorr_aggr, axis=0)
    return PVCueCorr_aggr