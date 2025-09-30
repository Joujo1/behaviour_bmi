import os
import sys
sys.path.insert(1, os.path.join(sys.path[0], '..'))
sys.path.insert(1, os.path.join(sys.path[0], '..', '..'))
sys.path.insert(1, os.path.join(sys.path[0], '..', '..', 'ephysVR'))

import shutil
from fuse import FUSE
import logging
import argparse

import pandas as pd

import analytics_processing.sessions_from_nas_parsing as sp
from analytics_processing.modality_loading import session_modality_from_nas
from CustomLogger import CustomLogger as Logger
from analytics_processing.analytics_constants import device_paths

from VirtualConcatFS import VirtualConcatFS

from ephysVR.mea1k_modules.mea1k_post_processing import write_prb_file
from ephysVR.mea1k_modules.mea1k_post_processing import write_prm_file

def create_virtual_concat(kwargs):
    def handle_path_setup(animal_id, traces_order, name):
        nas_dir = device_paths()[0]
        # everything in root will appear in the mount
        root = os.path.join(nas_dir, f"RUN_rYL{animal_id:03}", )
        concat_ss_base_dir = os.path.join(root, 'concatenated_ss')
        if not os.path.exists(concat_ss_base_dir):
            os.makedirs(concat_ss_base_dir) # created once per animal
        
        if not os.path.exists(os.path.join(concat_ss_base_dir, 'fused_concat_dat')):
            os.makedirs(os.path.join(concat_ss_base_dir, 'fused_concat_dat')) # created once per animal

        # define the dir name of this concatenated ss preparation, R/W in this dir
        datet = pd.to_datetime('now').strftime("%Y-%m-%d_%H-%M")
        this_ss_dirname = f"{datet}_rYL{animal_id:03}_{len(traces_order)}_concat_ss{name}"
        this_ss_fullpath = os.path.join(concat_ss_base_dir, this_ss_dirname)
        os.makedirs(this_ss_fullpath, exist_ok=True)
        L.logger.info(f"Created directory for concatenated ss: {this_ss_fullpath}")
        
        # the JRC parameter file
        # rat 006 updated_prms = {'ignoreChans': '[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 162, 163, 165, 166, 168, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 231, 232, 234, 235, 238, 239, 240, 241, 244, 246, 248, 249, 250, 252, 256, 257, 258, 259, 260, 265, 266, 270, 271, 272, 273, 274, 275, 277, 279, 287, 299, 303, 308, 316, 319, 320, 323, 325, 327, 328, 330, 331, 333, 336, 339, 340, 343, 344, 345, 346, 347, 348, 349, 350, 353, 360, 366, 373, 374, 376, 378, 382, 384, 385, 388, 389, 390, 391, 392, 393, 401, 402, 406, 409, 411, 413, 415, 416, 420, 421, 422, 428, 429];'}
        # rat 010 updated_prms = {'ignoreChans': '[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 108, 109, 112, 113, 116, 117, 120, 123, 124, 127, 128, 130, 131, 134, 135, 137, 138, 139, 140, 141, 142, 143, 145, 146, 147, 149, 150, 153, 154, 157, 158, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277, 278, 279, 280, 281, 282, 283, 284, 285, 286, 287, 288, 289, 290, 291, 292, 294, 295, 308, 309, 310, 312, 313, 314, 315, 316, 317, 318, 319, 320, 327, 328, 334, 336, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 350, 351, 352, 353, 354, 355, 357, 383, 384, 385, 386, 387, 388, 389, 390, 391, 392, 393, 394, 395, 396, 397, 398, 399, 400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414, 415, 416, 417, 418, 419, 420, 421, 422, 423, 424, 425, 426, 427, 428, 429, 430, 431, 432, 433, 434, 435, 436, 437, 438, 439, 440, 441, 442, 443, 444, 445, 446, 447, 448, 455, 456, 457, 458, 459, 460, 461, 462, 463, 464, 465, 466, 467, 468, 469, 470, 471, 472, 473, 474, 475, 476, 477, 478, 479, 480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490, 491, 492, 493, 494, 495, 496, 497, 498, 499, 500, 501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511, 512, 513, 514, 515, 516, 517, 518, 519, 520, 521, 522, 523, 524, 525, 526, 527, 528, 529, 530, 531, 532, 533, 534, 535, 536, 537, 538, 539, 540, 541, 542, 543, 544, 545, 546, 547, 548, 549, 550, 551, 552, 553, 554, 555, 556, 557, 558, 559, 560, 561, 562, 563, 564, 565, 566, 567, 568, 569, 570, 571, 572, 573, 574, 575, 576, 577, 578, 579, 580, 581, 582, 583, 584, 585, 586, 587, 588, 589, 590, 591, 592, 595, 598, 599, 601, 602, 603, 604, 605, 606, 607, 608, 611, 612, 615, 616, 620, 621, 625, 626, 628, 629, 630, 631, 632, 635, 636, 640, 641, 643, 644, 645, 646, 647, 648, 651, 655, 658, 659, 660, 661, 662, 663, 664, 665, 666, 667, 668, 669, 670, 671, 672, 673, 674, 675, 676, 677, 678, 681, 682, 683, 685, 688, 693, 697, 700, 702, 703, 704, 705, 706, 707, 708, 709, 710, 711, 712, 713, 714, 715, 716, 717, 722, 723, 724, 725, 726, 727, 728, 729, 730, 731, 732, 733, 734, 735, 737, 738];'}
        updated_prms = {'ignoreChans': '[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 108, 109, 112, 113, 116, 117, 120, 123, 124, 127, 128, 130, 131, 134, 135, 137, 138, 139, 140, 141, 142, 143, 145, 146, 147, 149, 150, 153, 154, 157, 158, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277, 278, 279, 280, 281, 282, 283, 284, 285, 286, 287, 288, 289, 290, 291, 292, 294, 295, 308, 309, 310, 312, 313, 314, 315, 316, 317, 318, 319, 320, 327, 328, 334, 336, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 350, 351, 352, 353, 354, 355, 357, 383, 384, 385, 386, 387, 388, 389, 390, 391, 392, 393, 394, 395, 396, 397, 398, 399, 400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414, 415, 416, 417, 418, 419, 420, 421, 422, 423, 424, 425, 426, 427, 428, 429, 430, 431, 432, 433, 434, 435, 436, 437, 438, 439, 440, 441, 442, 443, 444, 445, 446, 447, 448, 455, 456, 457, 458, 459, 460, 461, 462, 463, 464, 465, 466, 467, 468, 469, 470, 471, 472, 473, 474, 475, 476, 477, 478, 479, 480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490, 491, 492, 493, 494, 495, 496, 497, 498, 499, 500, 501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511, 512, 513, 514, 515, 516, 517, 518, 519, 520, 521, 522, 523, 524, 525, 526, 527, 528, 529, 530, 531, 532, 533, 534, 535, 536, 537, 538, 539, 540, 541, 542, 543, 544, 545, 546, 547, 548, 549, 550, 551, 552, 553, 554, 555, 556, 557, 558, 559, 560, 561, 562, 563, 564, 565, 566, 567, 568, 569, 570, 571, 572, 573, 574, 575, 576, 577, 578, 579, 580, 581, 582, 583, 584, 585, 586, 587, 588, 589, 590, 591, 592, 595, 598, 599, 601, 602, 603, 604, 605, 606, 607, 608, 611, 612, 615, 616, 620, 621, 625, 626, 628, 629, 630, 631, 632, 635, 636, 640, 641, 643, 644, 645, 646, 647, 648, 651, 655, 658, 659, 660, 661, 662, 663, 664, 665, 666, 667, 668, 669, 670, 671, 672, 673, 674, 675, 676, 677, 678, 681, 682, 683, 685, 688, 693, 697, 700, 702, 703, 704, 705, 706, 707, 708, 709, 710, 711, 712, 713, 714, 715, 716, 717, 722, 723, 724, 725, 726, 727, 728, 729, 730, 731, 732, 733, 734, 735, 737, 738];'}
        write_prm_file(mapping, out_fullfname=os.path.join(this_ss_fullpath, 'concat.prm'), 
                       shank_subset=shank_subset, updated_prms=updated_prms)
        # the probe file
        write_prb_file(mapping, os.path.join(this_ss_fullpath, 'concat.prb'),
                        shank_subset=shank_subset)
        # create the concat files that will be read by the FUSE
        open(os.path.join(concat_ss_base_dir, 'fused_concat_dat', 'concat.dat'), 'w').close()
        return this_ss_dirname, this_ss_fullpath, root

    L = Logger()
    # extract the arguments for paths for later
    nas_dir = device_paths()[0]
    mount = os.path.join(nas_dir, kwargs.pop('mount'))
    name = kwargs.pop('name')
    shank_subset = kwargs.pop('shank_subset', None)
    assert len(kwargs['animal_ids']) == 1, "Traces from only one animal can be concatenated"
    
    # get the matching sessions
    session_fullfnames, _ = sp.sessionlist_fullfnames_from_args(**kwargs)
    
    singlefiles_fullfnames = []
    singlefiles_lengths = []
    traces_order = None # set at first session
    for session_ffname in session_fullfnames:
        session_dir = os.path.dirname(session_ffname)
        d, mapping = session_modality_from_nas(session_ffname, key='ephys_traces')
        
        # valid session
        if mapping is not None:
            # first valid session, parse el order that is expected of all sessions
            if traces_order is None:
                L.logger.debug(f"Using mapping:\n{mapping}")
                traces_order = mapping['pad_id'].values
                # setup the paths, create base dir etc
                this_ss_dirname, this_ss_fullpath, root = handle_path_setup(kwargs['animal_ids'][0], 
                                                                            traces_order, name)
                
            # all follwing sessions
            else:
                # traces must exactly match the first session
                if (len(traces_order) != len(mapping) or 
                    not all(traces_order == mapping['pad_id'].values)):
                    L.logger.warning(f"Traces order of {os.path.basename(session_ffname)}"
                                     " differ from first session. Skipping.")
                    continue
            ephys_fname = [fn for fn in os.listdir(session_dir) 
                           if fn.startswith('20') and fn.endswith("ephys_traces.dat")][0]
            singlefiles_fullfnames.append(os.path.join(session_dir, ephys_fname))
            singlefiles_lengths.append((ephys_fname, d.shape[1]))

    if len(singlefiles_fullfnames) == 0:
        L.logger.error(f"No valid sessions found. Not mounting FUSE filesystem.")
        return
    L.spacer("debug")
    L.logger.debug(L.fmtmsg(["Files:", *singlefiles_fullfnames]))
    L.spacer("debug")
    
    # overview of the session boundaries
    singlefiles_lengths = pd.DataFrame(singlefiles_lengths, columns=['name','nsamples'])
    singlefiles_lengths['length_sec'] = singlefiles_lengths['nsamples'] // 20000
    singlefiles_lengths['length_sec_cum'] = singlefiles_lengths['length_sec'].cumsum()
    singlefiles_lengths['nsamples_cum'] = singlefiles_lengths['nsamples'].cumsum()
    
    singlefiles_lengths.to_csv(os.path.join(this_ss_fullpath, 'concat_session_lengths.csv'), index=False)

    L.logger.info(f"Mounting virtual filesystem for concatenated read of "
                  f"{len(singlefiles_fullfnames)} ephys traces at {mount}\n"
                  f"Spike sorting dir: {this_ss_fullpath}")
    L.spacer("info")
    logging.basicConfig(level=logging.INFO, )
    fuse_concat_fullfname = os.path.join('/', 'concatenated_ss', 'fused_concat_dat', 'concat.dat')
    FUSE(VirtualConcatFS(root, singlefiles_fullfnames=singlefiles_fullfnames,
                         concat_mount_fullfname=fuse_concat_fullfname,), 
         mount, 
         nothreads=True, 
         foreground=True)

def main():
    argParser = argparse.ArgumentParser("Mount a virtual file system to read concatenated ephys traces")
    argParser.add_argument("--animal_ids", nargs='+', type=int, required=True)
    argParser.add_argument("--paradigm_ids", nargs='+', default=None, type=int)
    argParser.add_argument("--session_names", nargs='+', default=None)
    argParser.add_argument("--from_date", default=None)
    argParser.add_argument("--to_date", default=None)
    argParser.add_argument("--logging_level", default="DEBUG")
    argParser.add_argument("--shank_subset", default=None, type=int, nargs='+')
    argParser.add_argument('--name', default="")
    argParser.add_argument('--mount', default="fuse_root")

    kwargs = vars(argParser.parse_args())
    L = Logger()
    Logger().init_logger(None, None, kwargs.pop("logging_level"))
    L.logger.info(f"Mounting virtual FS to read concatenated ephys traces")
    L.logger.debug(L.fmtmsg(kwargs))
    L.spacer()
    
    create_virtual_concat(kwargs)
    
if __name__ == '__main__':
    main()


# 2025-04-30_16-54_rYL010_P1100_LinearTrackStop_43min
# 2025-05-19_16-53_rYL010_P1100_LinearTrackStop_39min
# 2025-05-26_18-40_rYL010_P0000_AutoLickReward_73min
# 2025-06-04_16-00_rYL010_P0000_AutoLickReward_98min
# 2025-06-06_15-59_rYL010_P1100_LinearTrackStop_43min
# 2025-06-11_17-01_rYL010_P0000_PreSleepSessionWithLogger_10min
# 2025-06-13_13-20_rYL010_P1100_LinearTrackStop_28min