import pandas as pd
import json
import numpy as np

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from .general_plot_helpers import draw_track_illustration
from .general_plot_helpers import make_track_tuning_figure
from .general_plot_helpers import make_discr_trial_cmap

from dashsrc.components.dashvis_constants import *

def _parse_args(n_trials, group_by, metric, metric_max):
    # parse arguemnts and set defaults    
    if metric == 'Velocity':
        metric_col = 'posbin_velocity'
        y_axis_label = 'Velocity [cm/s]'
        y_axis_range = 0, metric_max
    elif metric == 'Acceleration':
        metric_col = 'posbin_acceleration'
        y_axis_label = 'Acceleration [cm/s^2]'
        y_axis_range = -metric_max, metric_max
    elif metric == 'Lick':
        metric_col = 'L_count'
        y_axis_label = 'Lick count'
        y_axis_range = 0, metric_max
    
    # Determine the color column and color mapping
    if group_by == 'Outcome':
        group_col, cmap = 'trial_outcome', OUTCOME_COL_MAP
    elif group_by == 'Cue':
        group_col, cmap = 'cue', CUE_COL_MAP
    elif group_by == 'Part of session':
        group_col = 'trial_id'
        cmap =  make_discr_trial_cmap(n_trials, TRIAL_COL_MAP)
    elif group_by == "None":
        group_col = "cue" # can be anything
        cmap = dict.fromkeys([1,2], "rgb(128,128,128)")
    # add transparency to the colors
    cmap_transparent = {k: v.replace("rgb","rgba")[:-1]+f', {MULTI_TRACES_ALPHA})' 
                        for k,v in cmap.items()}
    return metric_col, y_axis_label, y_axis_range, group_col, cmap, cmap_transparent

# def _make_figure():
    
#     # Create subplots with a slim top axis
#     fig = make_subplots(
#         rows=2, cols=1,
#         row_heights=[0.07, 0.93],  # Slim top axis
#         shared_xaxes=True,
#         vertical_spacing=0.02
#     )
#     return fig

def _configure_axis(fig, height, width, y_axis_range, y_axis_label):
    # Update layout for the main axis
    kwargs = {}
    if height != -1:
        kwargs['height'] = height
    if width != -1:
        kwargs['width'] = width
        
    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        autosize=True,
        margin=dict(l=0, r=0, t=0, b=0),  # Adjust margins as needed
        **kwargs,
    )
    
    # Update layout for the main axis
    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=0, r=0, t=0, b=0),  # Adjust margins as needed
        # width=800, height=400,
    )
    # fig.update_layout(
    #     plot_bgcolor='white',
    #     paper_bgcolor='white',
    #     autosize=True,
    #     **kwargs,
    # )
    
    fig.update_xaxes(
        showgrid=False,  # No x grid lines
        zeroline=False,
        showticklabels=True,
        title_text='Position [cm]',
        row=2, col=1
    )
    
    fig.update_yaxes(
        range=y_axis_range,
        showgrid=True,  # y grid lines
        gridwidth=1,
        gridcolor='LightGray',
        zeroline=True,
        zerolinewidth=2,
        zerolinecolor='LightGray',
        title_text=y_axis_label,
        row=2, col=1
    )
    return fig

def _draw_all_single_trials(fig, data, metric_col, cmap_transparent, group_col):
    # Create the main plot with line grouping by trial_id and color based on group_by
    for trial_id, trial_data in data.groupby('trial_id'):
        trace = go.Scatter(x=trial_data['from_position_bin'], 
                        y=trial_data[metric_col], mode='lines',
                        line=dict(color=cmap_transparent[trial_data[group_col].iloc[0]]),
                        name=f'Tr. {trial_id}')
        fig.add_trace(trace, row=2, col=1)

def _draw_percentile_area_plot(fig, upper_perc, lower_perc, metric_col, transp_color):
    # draw an area plot for the 80th percentile
    # draw essentially 2 lines and fill the area between them
    # print(upper_perc, lower_perc)
    fig.add_trace(go.Scatter(
        x=upper_perc['from_position_bin'].tolist() + lower_perc['from_position_bin'].tolist()[::-1],
        y=upper_perc[metric_col].tolist() + lower_perc[metric_col].tolist()[::-1],
        fill='toself',
        fillcolor=transp_color,
        mode='lines',
        line=dict(color='rgba(0,0,0,0)'),
        name='80th perc.',
    ), row=2, col=1)
    
def render_plot(track_data, fr, metadata, spike_metadata, n_sessions,
                metric_max, smooth_data, normalize_data, width=-1, height=-1):
    fr = fr.set_index(['trial_id', 'from_position_bin', 'cue', 'choice_R1', 'choice_R2'], append=True, )
    fr.drop(columns=['trial_outcome','bin_length'], inplace=True)
    fr.columns = fr.columns.astype(int)
    fr = fr.reindex(columns=sorted(fr.columns))
    
    print(fr)
    fr = fr.groupby(['from_position_bin', 'session_id']).mean().sort_index(level=['session_id', 'from_position_bin']).fillna(0)
    # print(fr)
    
    # fr.columns = fr.columns.astype(int)
    # fr = fr.reindex(columns=sorted(fr.columns))
    print(track_data)
    print(track_data.iloc[0])
    # print(metadata)
    # print(spike_metadata)
    print("================")
    # reorder to sorted columns
    
    cmap =  make_discr_trial_cmap(n_sessions, TRIAL_COL_MAP)
    
    unit_ids = fr.columns
    # unit_ids = (4,6,8,9,21,23,24,26,29)
    
    
    fig, height = make_track_tuning_figure(height=height, n_units=len(unit_ids))
    fig.update_layout(
        height=height,
    )
    
    session_ids = fr.index.unique('session_id')
    for i, cluster_id in enumerate(unit_ids):
    # for i, cluster_id in enumerate(fr.columns):
        print("\ncluster_id ", cluster_id)
        # if cluster_id not in (4,6,8,9,21,23,24,26,29): 
        #     continue
        
        # handle the data
        track_visrow = i*4 +1
        event_row = i*4 +2
        tuning_row = i*4 +3
        fig.update_yaxes(title_text=f"Neuron {i}", row=tuning_row, col=1)
        
        #TODO if P1100: choice_str='Stop', if DR == 1 draw_cues=[]
        min_track, max_track = track_data['from_position_bin'].min(), track_data['from_position_bin'].max()
        draw_track_illustration(fig, row=track_visrow, col=1,  track_details=json.loads(metadata.iloc[12]['track_details']), 
                                min_track=min_track, max_track=max_track, choice_str='Stop', draw_cues=[2], double_rewards=False)

        print()
        print()
        print()
        neuron_i_fr = fr.iloc[:, i].unstack(level='session_id').fillna(0).copy()
        print(neuron_i_fr)
        # neuron_i_fr.drop(columns=[10,24,25], inplace=True)
        neuron_i_fr.index = np.sort(track_data['from_position_bin'].unique())
        # if cluster_id == 24:
        #     print(neuron_i_fr)
        # neuron_i_fr = neuron_i_fr.drop(columns=[10, 25])

        # normalize data if ticked row wise
        if normalize_data:
            z_values = neuron_i_fr.T.values / neuron_i_fr.T.values.max(axis=1, keepdims=True)
            # z_values = np.log10(neuron_i_fr.T.values) # TODO Do we want log scaling as well?
        else: 
            z_values = neuron_i_fr.T.values
                    
        # do a heatmap instead
        fig.add_trace(
            go.Heatmap(
                z=z_values,
                x=neuron_i_fr.T.columns,
                y=neuron_i_fr.T.index,
                colorscale="Viridis",  # Color scale
                zmin=0,
                zmax=z_values.max(),
                showscale=False,
            ), row=tuning_row, col=1,
        )
        unit_metad = spike_metadata[spike_metadata['cluster_id'] == int(cluster_id)].iloc[0]
        
        # for j, session_id in enumerate(session_ids):
        #     # print("session_id ", session_id)
        #     # handle the data
        #     # Smooth the data with exponential moving average
        #     if smooth_data:
        #         neuron_i_fr[session_id] = neuron_i_fr[session_id].rolling(window=10, center=True, min_periods=1).mean()
            
        #     if i > 3:
        #         continue
            # print(neuron_i_fr[session_id])
            
            
            # session_allunits_metad = spike_metadata.loc[pd.IndexSlice[:,:,session_id]]
            # unit_metad = spike_metadata[session_allunits_metad['cluster_id'] == int(cluster_id)].iloc[0]
            # print(unit_metad)
            
            # Add the mean trace to the main plot
            # mean_trace = go.Scatter(
            #     x=neuron_i_fr.index,
            #     y=neuron_i_fr[session_id],
            #     mode='lines',
            #     opacity=0.7,
            #     line=dict(color=cmap[j], width=1),
            #     name=f'Session {session_id}'
            # )
            # fig.add_trace(mean_trace, row=tuning_row, col=1)

        ann = f"Neuron {unit_metad['cluster_id']:03d}" 
        ann += ", HP" if unit_metad['shank_id'] == 2 else ", mPFC"
        fig.update_yaxes(
            title_text=ann, 
            tickvals=neuron_i_fr.columns,
            autorange='reversed',
            ticktext=[f"S{s_id}" for s_id in neuron_i_fr.columns],
            row=tuning_row, col=1)
        fig.update_xaxes(
            range=(min_track, max_track),
            row=tuning_row, col=1
        )
        
        
        
        
        # event plot
        event_cnt = track_data.loc[:, ['from_position_bin', 'reward-removed_count', 'lick_count', 'reward-valve-open_count', #'S_count', 
                                      ]].groupby('from_position_bin').sum().astype(float).T
        # print(event_cnt)
        event_cnt /= event_cnt.max(axis=1).values[:, np.newaxis]
        # print(event_cnt)
        
        # small heatmap
        fig.add_trace(
            go.Heatmap(
                z=event_cnt.values,
                x=event_cnt.columns,
                y=event_cnt.index,
                colorscale="Greys",  # Color scale
                showscale=False,
            ), row=event_row, col=1,
        )
        
    
    return fig