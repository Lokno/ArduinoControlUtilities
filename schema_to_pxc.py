import os
import argparse

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Creates a Pixel Composer Project with a single struct from the provided key names")
    parser.add_argument("schema", help="Comma-delimited list (no spaces) of key names")
    parser.add_argument("-o","--output", default='myproject.pxc', help="Name of output file (default: myproject.pxc)")

    args = parser.parse_args()

    if args.schema is not None:
        struct_schema = args.schema.split(',')

        pxc_project_file_str = '{"graphGrid":{"size":32,"show":true,"opacity":0.050000000000000003,"snap":true,"color":16777215},"metadata":{"alias":"","author":"","description":"","contact":"","file_id":0,"tags":[],"version":11500,"aut_id":0},"animator":{"framerate":30,"frames_total":30},"onion_skin":{"range":[-1,1],"alpha":0.5,"enabled":false,"step":1,"color":[255,16711680],"on_top":true},"nodes":[{"id":"dNTEOe3096565TeEqVAOgi8FgHkVVBV5","x":-256,"type":"Node_Struct","inputs":['

        pins = []
        values = []
        types = []

        s = f'{{"global_use":false,"name":"Key","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{{}},"sep_axis":false,"on_end":0,"visible":false,"animators":[],"raw_value":[[0,"frame",[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}},'
        s += f'{{"global_use":false,"name":"frame value","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{{}},"sep_axis":false,"on_end":0,"visible":true,"animators":[],"raw_value":[[0,0,[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}},'
        pxc_project_file_str += s

        for name in struct_schema:
            s = f'{{"global_use":false,"name":"Key","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{{}},"sep_axis":false,"on_end":0,"visible":false,"animators":[],"raw_value":[[0,"pin_{name}",[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}},'
            s += f'{{"global_use":false,"name":"pin_{name} value","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{{}},"sep_axis":false,"on_end":0,"visible":true,"animators":[],"raw_value":[[0,0,[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}},'
            pins.append(s)

            s = f'{{"global_use":false,"name":"Key","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{{}},"sep_axis":false,"on_end":0,"visible":false,"animators":[],"raw_value":[[0,"value_{name}",[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}},'
            s += f'{{"global_use":false,"name":"value_{name} value","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{{}},"sep_axis":false,"on_end":0,"visible":true,"animators":[],"raw_value":[[0,0,[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}},'
            values.append(s)

            s = f'{{"global_use":false,"name":"Key","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{{}},"sep_axis":false,"on_end":0,"visible":false,"animators":[],"raw_value":[[0,"type_{name}",[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}},'
            s += f'{{"global_use":false,"name":"type_{name} value","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{{}},"sep_axis":false,"on_end":0,"visible":true,"animators":[],"raw_value":[[0,0,[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}},'
            types.append(s)

        pxc_project_file_str += ''.join(pins) + ''.join(values) + ''.join(types)

        pxc_project_file_str += '{"global_use":false,"name":"Key","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{},"sep_axis":false,"on_end":0,"visible":false,"animators":[],"raw_value":[[0,"",[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false},{"global_use":false,"name":"value","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{},"sep_axis":false,"on_end":0,"visible":false,"animators":[],"raw_value":[[0,0,[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}],"attri":{},"name":"Struct","input_fix_len":0,"iname":"Struct71660","preview":false,"render":true,"y":-224,"outputs":[{"visible":true}],"data_length":2,"inspectInputs":[{"global_use":false,"name":"Toggle execution","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{},"sep_axis":false,"on_end":0,"visible":true,"animators":[],"raw_value":[[0,false,[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false},{"global_use":false,"name":"Toggle execution","unit":0,"loop_range":-1,"shift_y":0,"from_index":-1,"data":{},"sep_axis":false,"on_end":0,"visible":true,"animators":[],"raw_value":[[0,false,[0,1],[0,0],0,0,true]],"shift_x":0,"global_key":"","from_node":-1,"anim":false}],"group":-4,"tool":false}],"addon":{},"preview":"","global_node":{"inputs":[]},"version":11500,"previewGrid":{"snap":false,"show":false,"opacity":0.5,"height":16,"width":16,"color":8482157}}'

        with open(args.output,'w') as f:
            f.write(pxc_project_file_str)