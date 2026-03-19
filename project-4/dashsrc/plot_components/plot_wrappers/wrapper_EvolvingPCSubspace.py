from dash import html, dcc, Input, Output, Dash
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np

from .. .components.dcc_graphs import get_general_graph_component
from .data_selection_components import (
    paradigm_dropdown_component,
    animal_dropdown_component,
    figure_width_input_component,
    figure_height_input_component,
    
    register_animal_dropdown_callback,
    register_paradigm_dropdown_callback,
)
from ..plots import plot_EvolvingPCSubspace
from dashsrc.components.plot_ui_components import get_ca_method_radioitems_component, get_vmin_input, get_vmax_input

import dashsrc.components.dashvis_constants as C

def render(app: Dash, global_data: dict, vis_name: str) -> html.Div:
    analytic = 'SessionPCs40ms'
    # components with data depedency need these arguments
    comp_args = vis_name, global_data, analytic
    
    # Register the callbacks
    register_paradigm_dropdown_callback(app, *comp_args)
    register_animal_dropdown_callback(app, *comp_args)
    
    # create the html components to have their IDs (needed for the callbacks)
    paradigm_dropd, PARADIGM_DROPD_ID = paradigm_dropdown_component(*comp_args, multi=True)
    animal_dropd, ANIMAL_DROPD_ID = animal_dropdown_component(*comp_args)
    
    height_input, HEIGHT_INP_ID = figure_height_input_component(vis_name)
    width_input, WIDTH_INP_ID = figure_width_input_component(vis_name)
    
    ca_method_radio = get_ca_method_radioitems_component(vis_name)
    CA_METHOD_ID = f'ca-method-{vis_name}'
    
    vmin_input = get_vmin_input(vis_name)
    VMIN_ID = f'vmin-input-{vis_name}'
    
    vmax_input = get_vmax_input(vis_name)
    VMAX_ID = f'vmax-input-{vis_name}'

    graph, GRAPH_ID = get_general_graph_component(vis_name, )
    
    @app.callback(
        Output(GRAPH_ID, 'figure'),
        Input(PARADIGM_DROPD_ID, 'value'),
        Input(ANIMAL_DROPD_ID, 'value'),
        Input(HEIGHT_INP_ID, 'value'),
        Input(WIDTH_INP_ID, 'value'),
        Input(CA_METHOD_ID, 'value'),
        Input(VMIN_ID, 'value'),
        Input(VMAX_ID, 'value'),
        )
    def update_plot(selected_paradigm, selected_animal, height, width, ca_method, vmin, vmax):

        if not all((selected_paradigm, selected_animal)):
            return {}
        
        # paradigm_slice = slice(selected_paradigm)
        # animal_slice = slice(selected_animal, selected_animal)
        
        # metadata
        metadata = global_data['SessionMetadata'].loc[[*selected_paradigm,]]

        PCs = global_data['SessionPCs40ms'].loc[[*selected_paradigm,]]
        CAs = global_data['SessionPCs40msCAs']

        fig = plot_EvolvingPCSubspace.render_plot(PCs, CAs, metadata, height, width, ca_method, vmin, vmax)
        return fig
    
    return html.Div([
        dcc.Store(id=C.get_vis_name_data_loaded_id(vis_name), data=False),  # Store to track data loading state
        dbc.Row([
            # Left side for plots
            dbc.Col([
                graph,
            ], width=10),
            # Right side for UI controls
            dbc.Col([
                # three rows, header, dropdown/tickpoxes, range slider
                dbc.Row([
                    html.H5(f"Data Selection for {vis_name}", style={"marginTop": 20}),
                ]),                                
                
                dbc.Row([
                    dbc.Col([
                        # Dropdown for paradigm selection, animal selection
                        *paradigm_dropd, *animal_dropd,
                        # Height, width, vmin, vmax inputs
                        *height_input, *width_input, *vmin_input, *vmax_input,
                    ], width=6),
                    
                    # Other options in right column
                    dbc.Col([
                        *ca_method_radio,
                    ], width=6),
                ]),
            ], width=2)
        ]),
        html.Hr()
    ], id=f"{vis_name}-container")  # Initial state is hidden